# routers/categories.py
from fastapi import ( APIRouter, Depends, HTTPException,
                      status, Request, Form )
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from urllib.parse import urlencode
import math

# Absolute Imports from project root (gofresh_stockpro)
import schemas # เข้าถึง schemas ผ่าน schemas.ClassName
from services import category_service
from database import get_db
# templates object จะถูกเข้าถึงผ่าน request.app.state.templates ในแต่ละ route

API_INCLUDE_IN_SCHEMA = True

router = APIRouter(
    tags=["API - หมวดหมู่สินค้า"],
    include_in_schema=API_INCLUDE_IN_SCHEMA
)

ui_router = APIRouter(
    tags=["หน้าเว็บ - หมวดหมู่สินค้า"],
    include_in_schema=False
)

# --- API Routes ---
@router.post("/", response_model=schemas.Category, status_code=status.HTTP_201_CREATED)
async def api_create_new_category(category: schemas.CategoryCreate, db: Session = Depends(get_db)):
    """สร้างหมวดหมู่สินค้าใหม่ (API)"""
    try:
        return category_service.create_category(db=db, category=category)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@router.get("/", response_model=List[schemas.Category])
async def api_read_all_categories(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """ดึงรายการหมวดหมู่สินค้าทั้งหมด (API)"""
    categories_data = category_service.get_categories(db, skip=skip, limit=limit)
    return categories_data["items"]

@router.get("/{category_id}", response_model=schemas.Category)
async def api_read_one_category(category_id: int, db: Session = Depends(get_db)):
    """ดึงข้อมูลหมวดหมู่ตามรหัส (API)"""
    db_category = category_service.get_category(db, category_id=category_id)
    if db_category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบหมวดหมู่รหัส {category_id}")
    return db_category

@router.put("/{category_id}", response_model=schemas.Category)
async def api_update_existing_category(category_id: int, category: schemas.CategoryCreate, db: Session = Depends(get_db)):
    """อัปเดตข้อมูลหมวดหมู่ตามรหัส (API)"""
    try:
        updated_category = category_service.update_category(db, category_id=category_id, category_update=category)
        if updated_category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบหมวดหมู่รหัส {category_id}")
        return updated_category
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@router.delete("/{category_id}", response_model=schemas.Category)
async def api_remove_category(category_id: int, db: Session = Depends(get_db)):
    """ลบหมวดหมู่ตามรหัส (API)"""
    try:
        deleted_category = category_service.delete_category(db, category_id=category_id)
        if deleted_category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบหมวดหมู่รหัส {category_id}")
        return deleted_category
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# --- UI Routes ---
@ui_router.get("/", response_class=HTMLResponse, name="ui_read_all_categories")
async def ui_read_all_categories(request: Request, page: int = 1, limit: int = 15, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    skip = (page - 1) * limit
    if skip < 0: skip = 0
    message = request.query_params.get('message')
    error = request.query_params.get('error')
    categories_data = category_service.get_categories(db=db, skip=skip, limit=limit)
    total_count = categories_data["total_count"]
    items = categories_data["items"]
    total_pages = math.ceil(total_count / limit) if limit > 0 else 0
    return templates.TemplateResponse("categories/list.html", {
        "request": request, "categories": items, "page": page, "limit": limit,
        "total_count": total_count, "total_pages": total_pages,
        "message": message, "error": error, "skip": skip
    })

@ui_router.get("/add", response_class=HTMLResponse, name="ui_show_add_category_form")
async def ui_show_add_category_form(request: Request):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    return templates.TemplateResponse("categories/add.html", {"request": request, "form_data": None, "error": None})

@ui_router.post("/add", response_class=HTMLResponse, name="ui_handle_add_category_form")
async def ui_handle_add_category_form(request: Request, db: Session = Depends(get_db), name: str = Form(...)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = {"name": name}
    try:
        category_data = schemas.CategoryCreate(**form_data_dict)
        category_service.create_category(db=db, category=category_data)
        success_message = f"เพิ่มหมวดหมู่ '{name}' เรียบร้อยแล้ว"
        query_params = urlencode({"message": success_message})
        redirect_url = f"{request.app.url_path_for('ui_read_all_categories')}?{query_params}"
        return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        return templates.TemplateResponse("categories/add.html", {"request": request, "error": str(e), "form_data": form_data_dict}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         print(f"Unexpected form error: {e}")
         return templates.TemplateResponse("categories/add.html", {"request": request, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิด", "form_data": form_data_dict}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@ui_router.post("/delete/{category_id}", name="ui_handle_delete_category")
async def ui_handle_delete_category(request: Request, category_id: int, db: Session = Depends(get_db)):
    error_message = None; success_message = None
    try:
        deleted_category = category_service.delete_category(db=db, category_id=category_id)
        if deleted_category is None: error_message = f"ไม่พบหมวดหมู่รหัส {category_id}"
        else: success_message = f"ลบหมวดหมู่ '{deleted_category.name}' (รหัส: {category_id}) เรียบร้อยแล้ว"
    except ValueError as e: error_message = str(e)
    except Exception as e:
        print(f"Error deleting category {category_id}: {e}"); error_message = f"เกิดข้อผิดพลาดขณะลบหมวดหมู่รหัส {category_id}"
    if success_message: query_params = urlencode({"message": success_message})
    elif error_message: query_params = urlencode({"error": error_message})
    else: query_params = urlencode({"error": "เกิดข้อผิดพลาดบางอย่าง"})
    redirect_url = f"{request.app.url_path_for('ui_read_all_categories')}?{query_params}"
    return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)

@ui_router.get("/edit/{category_id}", response_class=HTMLResponse, name="ui_show_edit_category_form")
async def ui_show_edit_category_form(request: Request, category_id: int, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    category = category_service.get_category(db, category_id=category_id)
    if category is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบหมวดหมู่รหัส {category_id}")
    return templates.TemplateResponse("categories/edit.html", {"request": request, "category": category, "form_data": None, "error": None})

@ui_router.post("/edit/{category_id}", response_class=HTMLResponse, name="ui_handle_edit_category_form")
async def ui_handle_edit_category_form(request: Request, category_id: int, db: Session = Depends(get_db), name: str = Form(...)):
     templates = request.app.state.templates
     if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
     form_data_dict = {"name": name}
     try:
        category_update_data = schemas.CategoryCreate(**form_data_dict)
        updated_category = category_service.update_category(db, category_id=category_id, category_update=category_update_data)
        if updated_category is None:
             query_params = urlencode({"error": f"ไม่พบหมวดหมู่รหัส {category_id} ที่ต้องการแก้ไข"})
             redirect_url = f"{request.app.url_path_for('ui_read_all_categories')}?{query_params}"
             return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)
        success_message = f"อัปเดตหมวดหมู่ '{updated_category.name}' (รหัส: {category_id}) เรียบร้อยแล้ว"
        query_params = urlencode({"message": success_message})
        redirect_url = f"{request.app.url_path_for('ui_read_all_categories')}?{query_params}"
        return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)
     except ValueError as e:
        category = category_service.get_category(db, category_id=category_id)
        if category is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบหมวดหมู่รหัส {category_id} ขณะจัดการข้อผิดพลาด")
        return templates.TemplateResponse("categories/edit.html", {"request": request, "category": category, "error": str(e), "form_data": form_data_dict }, status_code=status.HTTP_400_BAD_REQUEST)
     except Exception as e:
         category = category_service.get_category(db, category_id=category_id)
         print(f"Unexpected edit category error: {e}")
         context = {"request": request, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิด", "form_data": form_data_dict }
         if category: context["category"] = category
         return templates.TemplateResponse("categories/edit.html", context, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)