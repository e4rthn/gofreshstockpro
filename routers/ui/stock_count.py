# routers/ui/stock_count.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from urllib.parse import urlencode
import math

# Adjust imports
import schemas
import models
from services import stock_count_service, location_service, category_service, product_service
from database import get_db

# Define prefix here
ui_router = APIRouter(
    prefix="/ui/stock-counts",
    tags=["UI - ตรวจนับสต็อก"],
    include_in_schema=False
)

# --- UI Routes ---
@ui_router.get("/sessions/", response_class=HTMLResponse, name="ui_list_stock_count_sessions")
async def ui_list_stock_count_sessions(
    request: Request, page: int = Query(1, ge=1), limit: int = Query(15, ge=1), db: Session = Depends(get_db)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    skip = (page - 1) * limit
    if skip < 0: skip = 0
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
    redirect_url = "/ui/stock-counts/sessions/" # Fallback
    try:
        session_data = schemas.StockCountSessionCreate(**form_data_dict)
        new_session = stock_count_service.create_stock_count_session(db=db, session_data=session_data)
        success_message = f"สร้างรอบนับสต็อก #{new_session.id} สำหรับสถานที่ ID {location_id} เรียบร้อยแล้ว"
        query_params = urlencode({"message": success_message})
        try:
            redirect_url_path = request.app.url_path_for('ui_view_stock_count_session', session_id=new_session.id)
            redirect_url = f"{str(redirect_url_path)}?{query_params}"
        except Exception as redirect_err:
            print(f"Error creating redirect URL for session create success: {redirect_err}")
            # Fallback might go to list view if detail view URL fails
            try:
                 list_path = request.app.url_path_for('ui_list_stock_count_sessions')
                 redirect_url = f"{str(list_path)}?{query_params}"
            except: pass # Stick with default fallback

        return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e: # Location not found
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
    redirect_url = f"/ui/stock-counts/sessions/{session_id}" # Fallback
    try:
        item_data = schemas.StockCountItemCreate(product_id=product_id)
        created_item = stock_count_service.add_product_to_session(db=db, session_id=session_id, item_data=item_data)
        success_message = f"เพิ่มสินค้า ID {product_id} เข้ารอบนับ #{session_id} เรียบร้อยแล้ว (ยอดในระบบ: {created_item.system_quantity})"
    except ValueError as e: error_message = str(e)
    except Exception as e: print(f"Error adding item to session {session_id}: {e}"); error_message = "เกิดข้อผิดพลาดในการเพิ่มสินค้า"

    query_params_dict = {}
    if success_message: query_params_dict["message"] = success_message
    elif error_message: query_params_dict["error"] = error_message
    query_params = urlencode(query_params_dict)

    try:
        redirect_url_path = request.app.url_path_for('ui_view_stock_count_session', session_id=session_id)
        redirect_url = f"{str(redirect_url_path)}?{query_params}" if query_params else str(redirect_url_path)
    except Exception as redirect_err:
        print(f"Error creating redirect URL for add item: {redirect_err}")
        if query_params: redirect_url += f"?{query_params}"

    return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)


@ui_router.post("/sessions/{session_id}/start-counting", name="ui_start_counting_session")
async def ui_start_counting_session(request: Request, session_id: int, db: Session = Depends(get_db)):
    error_message = None; success_message = None
    redirect_url = f"/ui/stock-counts/sessions/{session_id}" # Fallback
    try:
        stock_count_service.start_counting_session(db, session_id=session_id)
        success_message = f"เริ่มดำเนินการนับสต็อกสำหรับรอบนับ #{session_id} แล้ว"
    except ValueError as e: error_message = str(e)
    except Exception as e: print(f"Error starting count session {session_id}: {e}"); error_message = "เกิดข้อผิดพลาดในการเริ่มนับสต็อก"

    query_params_dict = {}
    if success_message: query_params_dict["message"] = success_message
    elif error_message: query_params_dict["error"] = error_message
    query_params = urlencode(query_params_dict)

    try:
        redirect_url_path = request.app.url_path_for('ui_view_stock_count_session', session_id=session_id)
        redirect_url = f"{str(redirect_url_path)}?{query_params}" if query_params else str(redirect_url_path)
    except Exception as redirect_err:
        print(f"Error creating redirect URL for start counting: {redirect_err}")
        if query_params: redirect_url += f"?{query_params}"

    return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)

@ui_router.post("/sessions/{session_id}/update-counts", response_class=HTMLResponse, name="ui_handle_update_counts")
async def ui_handle_update_counts(request: Request, session_id: int, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data = await request.form(); errors = []; success_count = 0
    # Fetch session details needed for error re-rendering
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
                # Only add if value is not empty string, otherwise it means no count entered
                if value.strip() != "":
                    items_to_update.append({"item_id": item_id, "counted_quantity": counted_quantity})
            except (ValueError, IndexError): errors.append(f"ข้อมูลยอดนับสำหรับ '{key}' ไม่ถูกต้อง")

    if errors:
        # Re-render detail page with errors
        categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
        return templates.TemplateResponse("stock_count/session_detail.html", {"request": request, "session": session, "categories": categories, "error": "; ".join(errors)}, status_code=status.HTTP_400_BAD_REQUEST)

    # Process valid updates
    for item_update in items_to_update:
         if item_update["counted_quantity"] is not None: # Should always be true based on filter above
             try:
                 update_schema = schemas.StockCountItemUpdate(counted_quantity=item_update["counted_quantity"])
                 stock_count_service.update_counted_quantity(db, item_id=item_update["item_id"], item_update_data=update_schema)
                 success_count += 1
             except ValueError as e: errors.append(f"Item ID {item_update['item_id']}: {str(e)}")
             except Exception as e: errors.append(f"เกิดข้อผิดพลาดกับ Item ID {item_update['item_id']}: {str(e)}"); print(f"Error updating count item {item_update['item_id']}: {e}")

    # Prepare redirect URL with messages/errors
    query_params_dict = {}
    if errors: query_params_dict["error"] = "เกิดข้อผิดพลาดบางรายการ: " + "; ".join(errors)
    if success_count > 0: query_params_dict["message"] = f"บันทึกยอดนับ {success_count} รายการเรียบร้อยแล้ว"
    elif not errors: query_params_dict["message"] = "ไม่มีการเปลี่ยนแปลงยอดนับ"

    redirect_url = f"/ui/stock-counts/sessions/{session_id}" # Fallback
    query_params = urlencode(query_params_dict)
    try:
        redirect_url_path = request.app.url_path_for('ui_view_stock_count_session', session_id=session_id)
        redirect_url = f"{str(redirect_url_path)}?{query_params}" if query_params else str(redirect_url_path)
    except Exception as redirect_err:
        print(f"Error creating redirect URL for update counts: {redirect_err}")
        if query_params: redirect_url += f"?{query_params}"

    return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)

@ui_router.post("/sessions/{session_id}/close", name="ui_handle_close_session")
async def ui_handle_close_session(request: Request, session_id: int, db: Session = Depends(get_db)):
    error_message = None; success_message = None
    redirect_target_name = 'ui_view_stock_count_session' # Default to detail page on error
    redirect_params = {"session_id": session_id}
    try:
        closed_session = stock_count_service.close_stock_count_session(db=db, session_id=session_id)
        success_message = f"ปิดรอบนับสต็อก #{closed_session.id} และสร้างรายการปรับปรุงสต็อกเรียบร้อยแล้ว"
        redirect_target_name = 'ui_list_stock_count_sessions' # Redirect to list on success
        redirect_params = {} # No session_id needed for list view
    except ValueError as e: error_message = str(e)
    except Exception as e: print(f"Error closing session {session_id}: {e}"); error_message = f"เกิดข้อผิดพลาดในการปิดรอบนับสต็อก: {str(e)}"

    query_params_dict = {}
    if success_message: query_params_dict["message"] = success_message
    elif error_message: query_params_dict["error"] = error_message
    else: query_params_dict["error"] = "เกิดข้อผิดพลาดที่ไม่ทราบสาเหตุ" # Should not happen

    redirect_url = "/" # Absolute fallback
    query_params = urlencode(query_params_dict)
    try:
        redirect_url_path = request.app.url_path_for(redirect_target_name, **redirect_params)
        redirect_url = f"{str(redirect_url_path)}?{query_params}" if query_params else str(redirect_url_path)
    except Exception as redirect_err:
        print(f"Error creating redirect URL for close session: {redirect_err}")
        # Attempt fallback to list view URL with params
        try:
            list_path = request.app.url_path_for('ui_list_stock_count_sessions')
            redirect_url = f"{str(list_path)}?{query_params}" if query_params else str(list_path)
        except: # Final fallback
             redirect_url = f"/ui/stock-counts/sessions/?{query_params}" if query_params else "/ui/stock-counts/sessions/"

    return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)


@ui_router.post("/sessions/{session_id}/cancel", name="ui_handle_cancel_session")
async def ui_handle_cancel_session(request: Request, session_id: int, db: Session = Depends(get_db)):
    """ จัดการการยกเลิกรอบนับสต็อก """
    error_message = None; success_message = None
    redirect_target_name = 'ui_view_stock_count_session' # Default to detail page on error
    redirect_params = {"session_id": session_id}
    try:
        canceled_session = stock_count_service.cancel_stock_count_session(db=db, session_id=session_id)
        success_message = f"ยกเลิกรอบนับสต็อก #{canceled_session.id} เรียบร้อยแล้ว"
        redirect_target_name = 'ui_list_stock_count_sessions' # Redirect to list on success
        redirect_params = {}
    except ValueError as e: error_message = str(e)
    except Exception as e:
        print(f"Error canceling stock count session {session_id}: {e}")
        error_message = "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะยกเลิกรอบนับสต็อก"

    query_params_dict = {}
    if success_message: query_params_dict["message"] = success_message
    if error_message: query_params_dict["error"] = error_message

    redirect_url = "/" # Absolute fallback
    query_params = urlencode(query_params_dict)
    try:
        redirect_url_path = request.app.url_path_for(redirect_target_name, **redirect_params)
        redirect_url = f"{str(redirect_url_path)}?{query_params}" if query_params else str(redirect_url_path)
    except Exception as redirect_err:
         print(f"Error creating redirect URL for cancel session: {redirect_err}")
         # Attempt fallback to list view URL with params
         try:
             list_path = request.app.url_path_for('ui_list_stock_count_sessions')
             redirect_url = f"{str(list_path)}?{query_params}" if query_params else str(list_path)
         except: # Final fallback
              redirect_url = f"/ui/stock-counts/sessions/?{query_params}" if query_params else "/ui/stock-counts/sessions/"

    return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)