# routers/locations.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from urllib.parse import urlencode
import math

# Absolute Imports
import schemas
from services import location_service
from database import get_db
# templates object จะถูกเข้าถึงผ่าน request.app.state.templates ในแต่ละ route

API_INCLUDE_IN_SCHEMA = True

router = APIRouter(
    # prefix ถูกกำหนดใน main.py ตอน app.include_router
    tags=["API - สถานที่จัดเก็บ"],
    include_in_schema=API_INCLUDE_IN_SCHEMA
)

ui_router = APIRouter(
    # prefix ถูกกำหนดใน main.py ตอน app.include_router
    tags=["หน้าเว็บ - สถานที่จัดเก็บ"],
    include_in_schema=False
)

# --- API Routes ---
@router.post("/", response_model=schemas.Location, status_code=status.HTTP_201_CREATED)
async def api_create_new_location(location: schemas.LocationCreate, db: Session = Depends(get_db)):
    """สร้างสถานที่จัดเก็บใหม่ (API)"""
    try:
        return location_service.create_location(db=db, location=location)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@router.get("/", response_model=List[schemas.Location])
async def api_read_all_locations(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """ดึงรายการสถานที่จัดเก็บทั้งหมด (API)"""
    locations_data = location_service.get_locations(db, skip=skip, limit=limit)
    return locations_data["items"]

@router.get("/{location_id}", response_model=schemas.Location)
async def api_read_one_location(location_id: int, db: Session = Depends(get_db)):
    """ดึงข้อมูลสถานที่จัดเก็บตามรหัส (API)"""
    db_location = location_service.get_location(db, location_id=location_id)
    if db_location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสถานที่จัดเก็บรหัส {location_id}")
    return db_location

@router.put("/{location_id}", response_model=schemas.Location)
async def api_update_existing_location(location_id: int, location: schemas.LocationCreate, db: Session = Depends(get_db)):
    """อัปเดตข้อมูลสถานที่จัดเก็บ (API)"""
    try:
        updated_loc = location_service.update_location(db, location_id=location_id, location_update=location)
        if updated_loc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสถานที่รหัส {location_id}")
        return updated_loc
    except ValueError as e: # ชื่อซ้ำ
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@router.delete("/{location_id}", response_model=schemas.Location)
async def api_remove_location(location_id: int, db: Session = Depends(get_db)):
    """ลบสถานที่จัดเก็บ (API)"""
    try:
        deleted_loc = location_service.delete_location(db, location_id=location_id)
        if deleted_loc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสถานที่รหัส {location_id}")
        return deleted_loc # Service คืน Model object, Pydantic แปลงให้
    except ValueError as e: # ถูกใช้งานอยู่
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# --- UI Routes ---
@ui_router.get("/", response_class=HTMLResponse, name="ui_read_all_locations")
async def ui_read_all_locations(
    request: Request, page: int = 1, limit: int = 15, db: Session = Depends(get_db)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    skip = (page - 1) * limit
    if skip < 0: skip = 0
    message = request.query_params.get('message')
    error = request.query_params.get('error')
    locations_data = location_service.get_locations(db=db, skip=skip, limit=limit)
    total_count = locations_data["total_count"]
    items = locations_data["items"]
    total_pages = math.ceil(total_count / limit) if limit > 0 else 0
    return templates.TemplateResponse("locations/list.html", {
        "request": request, "locations": items, "page": page, "limit": limit,
        "total_count": total_count, "total_pages": total_pages,
        "message": message, "error": error, "skip": skip
    })

@ui_router.get("/add", response_class=HTMLResponse, name="ui_show_add_location_form")
async def ui_show_add_location_form(request: Request):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    return templates.TemplateResponse("locations/add.html", {"request": request, "form_data": None, "error": None})

@ui_router.post("/add", response_class=HTMLResponse, name="ui_handle_add_location_form")
async def ui_handle_add_location_form(
    request: Request, db: Session = Depends(get_db),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    discount_percent: Optional[float] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = {"name": name, "description": description, "discount_percent": discount_percent}
    try:
        location_data = schemas.LocationCreate(**form_data_dict)
        location_service.create_location(db=db, location=location_data)
        success_message = f"เพิ่มสถานที่ '{name}' เรียบร้อยแล้ว"
        query_params = urlencode({"message": success_message})
        redirect_url = f"{request.app.url_path_for('ui_read_all_locations')}?{query_params}"
        return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e: # ชื่อซ้ำ
        return templates.TemplateResponse("locations/add.html", {
            "request": request, "error": str(e), "form_data": form_data_dict
        }, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         print(f"Unexpected form error: {e}")
         return templates.TemplateResponse("locations/add.html", {
            "request": request, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะเพิ่มสถานที่", "form_data": form_data_dict
         }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@ui_router.get("/edit/{location_id}", response_class=HTMLResponse, name="ui_show_edit_location_form")
async def ui_show_edit_location_form(
    request: Request, location_id: int, db: Session = Depends(get_db)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    location = location_service.get_location(db, location_id=location_id)
    if location is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสถานที่รหัส {location_id}")
    return templates.TemplateResponse("locations/edit.html", {
        "request": request, "location": location, "form_data": None, "error": None
    })

@ui_router.post("/edit/{location_id}", response_class=HTMLResponse, name="ui_handle_edit_location_form")
async def ui_handle_edit_location_form(
    request: Request, location_id: int, db: Session = Depends(get_db),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    discount_percent: Optional[float] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = {"name": name, "description": description, "discount_percent": discount_percent}
    try:
        location_update_data = schemas.LocationCreate(**form_data_dict)
        updated_location = location_service.update_location(db, location_id=location_id, location_update=location_update_data)
        if updated_location is None:
             query_params = urlencode({"error": f"ไม่พบสถานที่รหัส {location_id} ที่ต้องการแก้ไข"})
             redirect_url = f"{request.app.url_path_for('ui_read_all_locations')}?{query_params}"
             return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)
        success_message = f"อัปเดตสถานที่ '{updated_location.name}' (รหัส: {location_id}) เรียบร้อยแล้ว"
        query_params = urlencode({"message": success_message})
        redirect_url = f"{request.app.url_path_for('ui_read_all_locations')}?{query_params}"
        return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e: # ชื่อซ้ำ
        location = location_service.get_location(db, location_id=location_id)
        if location is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสถานที่รหัส {location_id} ขณะจัดการข้อผิดพลาด")
        return templates.TemplateResponse("locations/edit.html", {
            "request": request, "location": location, "error": str(e), "form_data": form_data_dict
        }, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         location = location_service.get_location(db, location_id=location_id)
         print(f"Unexpected edit location error: {e}")
         context = {"request": request, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิด", "form_data": form_data_dict }
         if location: context["location"] = location
         return templates.TemplateResponse("locations/edit.html", context, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@ui_router.post("/delete/{location_id}", name="ui_handle_delete_location")
async def ui_handle_delete_location(
    request: Request, location_id: int, db: Session = Depends(get_db)
):
    error_message = None; success_message = None
    try:
        deleted_location = location_service.delete_location(db=db, location_id=location_id)
        if deleted_location is None: error_message = f"ไม่พบสถานที่รหัส {location_id}"
        else: success_message = f"ลบสถานที่ '{deleted_location.name}' (รหัส: {location_id}) เรียบร้อยแล้ว"
    except ValueError as e: error_message = str(e)
    except Exception as e:
        print(f"Error deleting location {location_id}: {e}"); error_message = f"เกิดข้อผิดพลาดขณะลบสถานที่รหัส {location_id}"
    if success_message: query_params = urlencode({"message": success_message})
    elif error_message: query_params = urlencode({"error": error_message})
    else: query_params = urlencode({"error": "เกิดข้อผิดพลาดบางอย่าง"})
    redirect_url = f"{request.app.url_path_for('ui_read_all_locations')}?{query_params}"
    return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)