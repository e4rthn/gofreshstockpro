# routers/stock_count.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload, subqueryload
from typing import List, Optional, Dict, Any
from urllib.parse import urlencode
import math

# Absolute Imports
import schemas
import models
from services import stock_count_service, location_service, category_service, product_service
from database import get_db
# templates เข้าถึงผ่าน request.app.state.templates

API_INCLUDE_IN_SCHEMA = True

router = APIRouter(
    # prefix="/api/stock-counts", # Prefix กำหนดใน main.py
    tags=["API - ตรวจนับสต็อก"],
    include_in_schema=API_INCLUDE_IN_SCHEMA
)
ui_router = APIRouter(
    prefix="/ui/stock-counts", # Prefix สำหรับ UI Routes ของ Stock Count
    tags=["หน้าเว็บ - ตรวจนับสต็อก"],
    include_in_schema=False
)

# --- Session API Routes ---
@router.post("/sessions/", response_model=schemas.StockCountSession, status_code=status.HTTP_201_CREATED)
async def api_create_new_stock_count_session(
    session_in: schemas.StockCountSessionCreate, db: Session = Depends(get_db)
):
    """ สร้างรอบนับสต็อกใหม่ (API) """
    try:
        new_session = stock_count_service.create_stock_count_session(db=db, session_data=session_in)
        # Query ใหม่เพื่อให้ได้ Location ตาม Response Model
        session_with_details = db.query(models.StockCountSession).options(
            joinedload(models.StockCountSession.location)
        ).filter(models.StockCountSession.id == new_session.id).first()
        if not session_with_details: raise HTTPException(status_code=500, detail="Could not fetch created session with location")
        return session_with_details
    except ValueError as e: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        print(f"Error creating count session (API): {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดในการสร้างรอบนับสต็อก")

@router.get("/sessions/", response_model=List[schemas.StockCountSessionInList])
async def api_get_all_stock_count_sessions(
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """ ดึงรายการรอบนับสต็อกทั้งหมด (API) """
    sessions_data = stock_count_service.get_stock_count_sessions(db, skip=skip, limit=limit)
    return sessions_data["items"]

@router.get("/sessions/{session_id}", response_model=schemas.StockCountSession)
async def api_get_one_stock_count_session(session_id: int, db: Session = Depends(get_db)):
    """ ดึงข้อมูลรอบนับสต็อกตาม ID (API) """
    session = stock_count_service.get_stock_count_session(db, session_id=session_id)
    if session is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    return session

# --- Item API Routes ---
@router.post("/sessions/{session_id}/items", response_model=schemas.StockCountItem, status_code=status.HTTP_201_CREATED)
async def api_add_item_to_session(
    session_id: int, item_in: schemas.StockCountItemCreate, db: Session = Depends(get_db)
):
    """ เพิ่มสินค้าเข้ารอบนับสต็อก (API) """
    try:
        created_item = stock_count_service.add_product_to_session(db=db, session_id=session_id, item_data=item_in)
        # Query ใหม่เพื่อให้ได้ Product ตาม Response Model
        item_with_details = db.query(models.StockCountItem).options(
            joinedload(models.StockCountItem.product) # โหลด product basic
        ).filter(models.StockCountItem.id == created_item.id).first()
        if not item_with_details: raise HTTPException(status_code=500, detail="Could not fetch created item with product")
        return item_with_details
    except ValueError as e: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(f"Error adding item to session (API) {session_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดในการเพิ่มสินค้ารอบนับสต็อก")

@router.patch("/items/{item_id}", response_model=schemas.StockCountItem)
async def api_update_item_count(
    item_id: int, item_update: schemas.StockCountItemUpdate, db: Session = Depends(get_db)
):
    """ อัปเดตยอดนับจริงของรายการสินค้า (API) """
    try:
        updated_item = stock_count_service.update_counted_quantity(db=db, item_id=item_id, item_update_data=item_update)
        item_with_details = db.query(models.StockCountItem).options(joinedload(models.StockCountItem.product)).filter(models.StockCountItem.id == updated_item.id).first()
        if not item_with_details: raise HTTPException(status_code=500, detail="Could not fetch updated item with product")
        return item_with_details
    except ValueError as e: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(f"Error updating count item (API) {item_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดในการบันทึกยอดนับ")

@router.post("/sessions/{session_id}/close", response_model=schemas.StockCountSession)
async def api_close_session_and_adjust(session_id: int, db: Session = Depends(get_db)):
    """ ปิดรอบนับสต็อกและสร้าง Adjustment อัตโนมัติ (API) """
    try:
        closed_session = stock_count_service.close_stock_count_session(db=db, session_id=session_id)
        # Query ใหม่เพื่อให้ได้ข้อมูลครบตาม Response Model (รวม items และอื่นๆ)
        session_with_details = stock_count_service.get_stock_count_session(db, session_id=closed_session.id)
        if not session_with_details: raise HTTPException(status_code=500, detail="Could not fetch closed session details")
        return session_with_details
    except ValueError as e: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(f"Error closing session (API) {session_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดในการปิดรอบนับสต็อก")

# --- UI Routes ---
@ui_router.get("/sessions/", response_class=HTMLResponse, name="ui_list_stock_count_sessions")
async def ui_list_stock_count_sessions(
    request: Request, page: int = 1, limit: int = 15, db: Session = Depends(get_db)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    skip = (page - 1) * limit; # ... (pagination logic)
    message = request.query_params.get('message'); error = request.query_params.get('error')
    sessions_data = stock_count_service.get_stock_count_sessions(db, skip=skip, limit=limit)
    total_count = sessions_data["total_count"]; items = sessions_data["items"]
    total_pages = math.ceil(total_count / limit) if limit > 0 else 0
    return templates.TemplateResponse("stock_count/sessions_list.html", {"request": request, "sessions": items, "page": page, "limit": limit, "total_count": total_count, "total_pages": total_pages, "message": message, "error": error, "skip": skip})

@ui_router.get("/sessions/new", response_class=HTMLResponse, name="ui_show_create_session_form")
async def ui_show_create_session_form(request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
    return templates.TemplateResponse("stock_count/session_create.html", {"request": request, "locations": locations, "form_data": None, "error": None})

@ui_router.post("/sessions/new", response_class=HTMLResponse, name="ui_handle_create_session_form")
async def ui_handle_create_session_form(
    request: Request, db: Session = Depends(get_db), location_id: int = Form(...), notes: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = {"location_id": location_id, "notes": notes}
    try:
        session_data = schemas.StockCountSessionCreate(**form_data_dict)
        new_session = stock_count_service.create_stock_count_session(db=db, session_data=session_data)
        success_message = f"สร้างรอบนับสต็อก #{new_session.id} สำหรับสถานที่ ID {location_id} เรียบร้อยแล้ว"
        query_params = urlencode({"message": success_message})
        redirect_url = f"{request.app.url_path_for('ui_view_stock_count_session', session_id=new_session.id)}?{query_params}"
        return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         return templates.TemplateResponse("stock_count/session_create.html", {"request": request, "locations": locations, "error": str(e), "form_data": form_data_dict}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         print(f"Unexpected create session error: {e}")
         return templates.TemplateResponse("stock_count/session_create.html", {"request": request, "locations": locations, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะสร้างรอบนับสต็อก", "form_data": form_data_dict}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@ui_router.get("/sessions/{session_id}", response_class=HTMLResponse, name="ui_view_stock_count_session")
async def ui_view_stock_count_session(request: Request, session_id: int, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    session = stock_count_service.get_stock_count_session(db, session_id=session_id)
    if session is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
    message = request.query_params.get('message'); error = request.query_params.get('error')
    return templates.TemplateResponse("stock_count/session_detail.html", {"request": request, "session": session, "categories": categories, "message": message, "error": error})

@ui_router.post("/sessions/{session_id}/items/add", name="ui_handle_add_item_to_session")
async def ui_handle_add_item_to_session(request: Request, session_id: int, db: Session = Depends(get_db), product_id: int = Form(...)):
    error_message = None; success_message = None
    try:
        item_data = schemas.StockCountItemCreate(product_id=product_id)
        created_item = stock_count_service.add_product_to_session(db=db, session_id=session_id, item_data=item_data)
        success_message = f"เพิ่มสินค้า ID {product_id} เข้ารอบนับ #{session_id} เรียบร้อยแล้ว (ยอดในระบบ: {created_item.system_quantity})"
    except ValueError as e: error_message = str(e)
    except Exception as e: print(f"Error adding item to session {session_id}: {e}"); error_message = "เกิดข้อผิดพลาดในการเพิ่มสินค้า"
    if success_message: query_params = urlencode({"message": success_message})
    elif error_message: query_params = urlencode({"error": error_message})
    else: query_params = ""
    redirect_url = f"{request.app.url_path_for('ui_view_stock_count_session', session_id=session_id)}?{query_params}"
    return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)

@ui_router.post("/sessions/{session_id}/start-counting", name="ui_start_counting_session")
async def ui_start_counting_session(request: Request, session_id: int, db: Session = Depends(get_db)):
    error_message = None; success_message = None
    try:
        stock_count_service.start_counting_session(db, session_id=session_id)
        success_message = f"เริ่มดำเนินการนับสต็อกสำหรับรอบนับ #{session_id} แล้ว"
    except ValueError as e: error_message = str(e)
    except Exception as e: print(f"Error starting count session {session_id}: {e}"); error_message = "เกิดข้อผิดพลาดในการเริ่มนับสต็อก"
    if success_message: query_params = urlencode({"message": success_message})
    elif error_message: query_params = urlencode({"error": error_message})
    else: query_params = ""
    redirect_url = f"{request.app.url_path_for('ui_view_stock_count_session', session_id=session_id)}?{query_params}"
    return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)

@ui_router.post("/sessions/{session_id}/update-counts", response_class=HTMLResponse, name="ui_handle_update_counts")
async def ui_handle_update_counts(request: Request, session_id: int, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data = await request.form(); errors = []; success_count = 0
    session = stock_count_service.get_stock_count_session(db, session_id=session_id)
    if not session: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    items_to_update = []
    for key, value in form_data.items():
        if key.startswith("count_for_"):
            try:
                item_id = int(key.split("_")[-1]); counted_quantity: Optional[int] = None
                if value.strip() != "":
                    counted_quantity = int(value)
                    if counted_quantity < 0: errors.append(f"ยอดนับของ Item ID {item_id} ต้องไม่ติดลบ"); continue
                items_to_update.append({"item_id": item_id, "counted_quantity": counted_quantity})
            except (ValueError, IndexError): errors.append(f"ข้อมูลยอดนับสำหรับ '{key}' ไม่ถูกต้อง")
    if errors:
        categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
        return templates.TemplateResponse("stock_count/session_detail.html", {"request": request, "session": session, "categories": categories, "error": "; ".join(errors)}, status_code=status.HTTP_400_BAD_REQUEST)
    for item_update in items_to_update:
         if item_update["counted_quantity"] is not None:
             try:
                 update_schema = schemas.StockCountItemUpdate(counted_quantity=item_update["counted_quantity"])
                 stock_count_service.update_counted_quantity(db, item_id=item_update["item_id"], item_update_data=update_schema)
                 success_count += 1
             except ValueError as e: errors.append(f"Item ID {item_update['item_id']}: {str(e)}")
             except Exception as e: errors.append(f"เกิดข้อผิดพลาดกับ Item ID {item_update['item_id']}: {str(e)}"); print(f"Error updating count item {item_update['item_id']}: {e}")
    query_params_dict = {}
    if errors: query_params_dict["error"] = "เกิดข้อผิดพลาดบางรายการ: " + "; ".join(errors)
    if success_count > 0: query_params_dict["message"] = f"บันทึกยอดนับ {success_count} รายการเรียบร้อยแล้ว"
    elif not errors: query_params_dict["message"] = "ไม่มีการเปลี่ยนแปลงยอดนับ"
    query_params = urlencode(query_params_dict)
    redirect_url = f"{request.app.url_path_for('ui_view_stock_count_session', session_id=session_id)}?{query_params}"
    return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)

@ui_router.post("/sessions/{session_id}/close", name="ui_handle_close_session")
async def ui_handle_close_session(request: Request, session_id: int, db: Session = Depends(get_db)):
    error_message = None; success_message = None
    try:
        closed_session = stock_count_service.close_stock_count_session(db=db, session_id=session_id)
        success_message = f"ปิดรอบนับสต็อก #{closed_session.id} และสร้างรายการปรับปรุงสต็อกเรียบร้อยแล้ว"
    except ValueError as e: error_message = str(e)
    except Exception as e: print(f"Error closing session {session_id}: {e}"); error_message = f"เกิดข้อผิดพลาดในการปิดรอบนับสต็อก: {str(e)}"
    if success_message:
        query_params = urlencode({"message": success_message})
        redirect_url = f"{request.app.url_path_for('ui_list_stock_count_sessions')}?{query_params}"
        return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)
    else:
        query_params = urlencode({"error": error_message or "เกิดข้อผิดพลาดที่ไม่ทราบสาเหตุ"})
        redirect_url = f"{request.app.url_path_for('ui_view_stock_count_session', session_id=session_id)}?{query_params}"
        return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)

@ui_router.post("/sessions/{session_id}/cancel", name="ui_handle_cancel_session")
async def ui_handle_cancel_session(request: Request, session_id: int, db: Session = Depends(get_db)):
    """ จัดการการยกเลิกรอบนับสต็อก """
    error_message = None; success_message = None
    try:
        canceled_session = stock_count_service.cancel_stock_count_session(db=db, session_id=session_id)
        success_message = f"ยกเลิกรอบนับสต็อก #{canceled_session.id} เรียบร้อยแล้ว"
    except ValueError as e: error_message = str(e)
    except Exception as e:
        print(f"Error canceling stock count session {session_id}: {e}")
        error_message = "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะยกเลิกรอบนับสต็อก"
    
    query_params_dict = {}
    if success_message: query_params_dict["message"] = success_message
    if error_message: query_params_dict["error"] = error_message
    
    query_params = urlencode(query_params_dict)
    # ถ้า error เพราะสถานะไม่ถูกต้อง หรือ error อื่นๆ ให้กลับไปหน้า detail
    # ถ้าสำเร็จ ให้กลับไปหน้า list
    redirect_target_name = 'ui_list_stock_count_sessions' if success_message else 'ui_view_stock_count_session'
    
    if redirect_target_name == 'ui_view_stock_count_session':
        redirect_url = f"{request.app.url_path_for(redirect_target_name, session_id=session_id)}?{query_params}"
    else:
        redirect_url = f"{request.app.url_path_for(redirect_target_name)}?{query_params}"
        
    return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)