# routers/ui/inventory.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import date, timedelta, datetime, time # Ensure datetime is imported
from urllib.parse import urlencode as python_urlencode
import math
import json # For session data

import schemas # Import the main schemas module
from schemas.inventory import BatchStockInSchema, StockInItemDetailSchema # Specific schemas
import models
from models import TransactionType # Ensure TransactionType is imported
from services import inventory_service, product_service, category_service, location_service
from database import get_db

try:
    from utils import format_thai_datetime, format_thai_date 
except ImportError:
    def format_thai_datetime(value, format_str="%d/%m/%Y %H:%M"): return str(value) if value else '-'
    def format_thai_date(value, format_str="%d/%m/%Y"): return str(value) if value else '-'
    print("Warning: Could not import time formatting functions from utils.py. Using fallback.")

ui_router = APIRouter(
    prefix="/ui/inventory",
    tags=["UI - สต็อกสินค้า"],
    include_in_schema=False
)

# --- ui_view_inventory_summary (No changes from previous versions you provided) ---
@ui_router.get("/summary/", response_class=HTMLResponse, name="ui_view_inventory_summary")
async def ui_view_inventory_summary(
    request: Request, page: int = Query(1, ge=1), limit: int = Query(15, ge=1),
    category_str: Optional[str] = Query(None, alias="category"), location_str: Optional[str] = Query(None, alias="location"),
    db: Session = Depends(get_db)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    skip = (page - 1) * limit; skip = max(0, skip)
    category_id: Optional[int] = None; location_id: Optional[int] = None
    try: category_id = int(category_str) if category_str and category_str.strip() else None
    except ValueError: pass
    try: location_id = int(location_str) if location_str and location_str.strip() else None
    except ValueError: pass

    report_data = inventory_service.get_current_stock_summary(db, skip=skip, limit=limit, category_id=category_id, location_id=location_id)
    items_orm = report_data.get("items", [])
    total_count = report_data.get("total_count", 0)
    total_pages = math.ceil(total_count / limit) if limit > 0 else 0
    all_categories_data = category_service.get_categories(db=db, limit=1000); all_categories = all_categories_data.get("items", [])
    all_locations_data = location_service.get_locations(db=db, limit=1000); all_locations = all_locations_data.get("items", [])

    formatted_items = []
    for item_orm in items_orm:
        try:
            item_display_dict = {
                "quantity": item_orm.quantity,
                "last_updated_formatted": format_thai_datetime(item_orm.last_updated, format_str='%d/%m/%y %H:%M'),
                "product_id": item_orm.product.id if item_orm.product else None,
                "product_name": item_orm.product.name if item_orm.product else 'N/A',
                "product_sku": item_orm.product.sku if item_orm.product else 'N/A',
                "product_shelf_life_days": item_orm.product.shelf_life_days if item_orm.product and item_orm.product.shelf_life_days is not None else '-',
                "category_name": item_orm.product.category.name if item_orm.product and item_orm.product.category else 'N/A',
                "location_name": item_orm.location.name if item_orm.location else 'N/A'
            }
            formatted_items.append(item_display_dict)
        except Exception as e:
            print(f"Error processing stock summary item for display: {e}")

    context = {
        "request": request, "stock_summary": formatted_items,
        "page": page, "limit": limit, "total_count": total_count, "total_pages": total_pages,
        "message": request.query_params.get('message'), "error": request.query_params.get('error'),
        "skip": skip, "all_categories": all_categories, "selected_category_id": category_id,
        "all_locations": all_locations, "selected_location_id": location_id
    }
    return templates.TemplateResponse("inventory/summary.html", context)


# --- Batch Stock-In Routes (New and Modified) ---
@ui_router.get("/stock-in", response_class=HTMLResponse, name="ui_show_stock_in_form")
async def ui_show_stock_in_form(request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    
    locations_data = location_service.get_locations(db=db, limit=1000)
    categories_data = category_service.get_categories(db=db, limit=1000)
    
    form_data_raw_json = request.session.pop("stock_in_form_data_raw", None)
    error_message = request.session.pop("stock_in_error_message", None)
    
    form_data_raw = None
    if form_data_raw_json:
        try:
            form_data_raw = json.loads(form_data_raw_json)
        except json.JSONDecodeError:
            print("Warning: Could not decode stock_in_form_data_raw from session.")
            form_data_raw = None # Ensure it's None if decode fails

    return templates.TemplateResponse(
        "inventory/stock_in.html", # This template is now designed for batch stock-in
        {
            "request": request,
            "locations": locations_data.get("items", []),
            "categories": categories_data.get("items", []),
            "error": error_message or request.query_params.get('error'),
            "message": request.query_params.get('message'),
            "form_data_raw": form_data_raw 
        }
    )

@ui_router.post("/stock-in/process-details", name="ui_process_stock_in_details_for_review")
async def ui_process_stock_in_details_for_review(
    request: Request, 
    db: Session = Depends(get_db) 
):
    form_data_dict = await request.form() 
    form_data = dict(form_data_dict) # Convert FormData to a regular dict for easier processing

    parsed_items: List[StockInItemDetailSchema] = []
    
    try:
        location_id_str = form_data.get("location_id")
        if not location_id_str or not location_id_str.strip().isdigit():
            raise ValueError("กรุณาเลือกสถานที่จัดเก็บที่ถูกต้อง")
        location_id = int(location_id_str)
        
        batch_notes_val = form_data.get("batch_notes")

        item_count = 0
        # Loop based on presence of items[INDEX][product_id]
        while True:
            prod_id_form_key = f"items[{item_count}][product_id]"
            if prod_id_form_key not in form_data:
                break 
            
            prod_id_str = form_data.get(prod_id_form_key)
            qty_str = form_data.get(f"items[{item_count}][quantity]")

            if not prod_id_str or not prod_id_str.strip().isdigit() or \
               not qty_str or not qty_str.strip(): # Basic check
                item_count += 1
                print(f"Skipping malformed item at index {item_count-1}")
                continue 

            product_id = int(prod_id_str)
            try:
                quantity = float(qty_str)
                if quantity <= 0:
                    raise ValueError("จำนวนต้องมากกว่า 0")
            except ValueError:
                 raise ValueError(f"รูปแบบจำนวนไม่ถูกต้องสำหรับสินค้า ID {product_id}")


            product_details = product_service.get_product(db, product_id=product_id)
            if not product_details:
                raise ValueError(f"ไม่พบข้อมูลสินค้าสำหรับ ID: {product_id}")

            cost_str = form_data.get(f"items[{item_count}][cost_per_unit]")
            prod_date_str = form_data.get(f"items[{item_count}][production_date]")
            exp_date_str = form_data.get(f"items[{item_count}][expiry_date]")
            # item_notes_str = form_data.get(f"items[{item_count}][notes]") # Notes per item removed based on user feedback

            item_schema_data = {
                "product_id": product_id,
                "quantity": quantity,
                "cost_per_unit": float(cost_str) if cost_str and cost_str.strip() else None,
                "production_date": date.fromisoformat(prod_date_str) if prod_date_str and prod_date_str.strip() else None,
                "expiry_date": date.fromisoformat(exp_date_str) if exp_date_str and exp_date_str.strip() else None,
                "notes": None, # Individual item notes removed
                "product_name": product_details.name,
                "product_sku": product_details.sku,
                "shelf_life_days": product_details.shelf_life_days
            }
            # Validate with Pydantic before adding
            item_schema = StockInItemDetailSchema(**item_schema_data)
            parsed_items.append(item_schema)
            item_count += 1
        
        if not parsed_items:
            raise ValueError("ไม่มีรายการสินค้าสำหรับการรับเข้า กรุณาเพิ่มสินค้าและกรอกรายละเอียด")

        batch_schema_for_session = BatchStockInSchema(
            location_id=location_id,
            items=parsed_items,
            batch_notes=batch_notes_val
        )
        request.session["batch_stock_in_data"] = batch_schema_for_session.model_dump(mode='json')
        
        return RedirectResponse(url=request.app.url_path_for('ui_show_stock_in_review_page'), status_code=status.HTTP_303_SEE_OTHER)

    except ValueError as ve:
        request.session["stock_in_error_message"] = str(ve)
        request.session["stock_in_form_data_raw"] = json.dumps(form_data) # Store original form_data
        return RedirectResponse(url=request.app.url_path_for('ui_show_stock_in_form'), status_code=status.HTTP_303_SEE_OTHER)
    except Exception as ex:
        print(f"Error processing stock-in details: {type(ex).__name__} - {ex}")
        request.session["stock_in_error_message"] = "เกิดข้อผิดพลาดในการประมวลผลข้อมูล โปรดลองอีกครั้ง"
        request.session["stock_in_form_data_raw"] = json.dumps(form_data)
        return RedirectResponse(url=request.app.url_path_for('ui_show_stock_in_form'), status_code=status.HTTP_303_SEE_OTHER)


@ui_router.get("/stock-in/review", response_class=HTMLResponse, name="ui_show_stock_in_review_page")
async def ui_show_stock_in_review_page(request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")

    batch_data_dict_from_session = request.session.get("batch_stock_in_data")
    if not batch_data_dict_from_session:
        error_query_params = python_urlencode({"error": "ไม่พบข้อมูล Batch สำหรับตรวจสอบ กรุณาเริ่มต้นใหม่"})
        return RedirectResponse(url=f"{request.app.url_path_for('ui_show_stock_in_form')}?{error_query_params}", status_code=status.HTTP_303_SEE_OTHER)
    
    try:
        # Reconstruct the Pydantic model from the dictionary stored in session
        batch_data_for_template = BatchStockInSchema.model_validate(batch_data_dict_from_session)
        
        location_obj = location_service.get_location(db, location_id=batch_data_for_template.location_id)
        location_name_for_display = location_obj.name if location_obj else f"ID: {batch_data_for_template.location_id}"

    except Exception as e: 
        print(f"Error validating batch data from session for review: {type(e).__name__} - {e}")
        request.session.pop("batch_stock_in_data", None) 
        error_query_params = python_urlencode({"error": "ข้อมูล Batch ใน Session ไม่ถูกต้อง กรุณาเริ่มต้นใหม่"})
        return RedirectResponse(url=f"{request.app.url_path_for('ui_show_stock_in_form')}?{error_query_params}", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "inventory/stock_in_review.html", # New template for review page
        {
            "request": request,
            "batch_data": batch_data_for_template, 
            "location_name": location_name_for_display,
            "error": request.query_params.get('error'), 
            "message": request.query_params.get('message'),
            "timedelta": timedelta # Pass timedelta for date calculations in template
        }
    )

@ui_router.post("/stock-in/confirm", name="ui_confirm_batch_stock_in")
async def ui_confirm_batch_stock_in(request: Request, db: Session = Depends(get_db)):
    batch_data_dict = request.session.pop("batch_stock_in_data", None) 
    if not batch_data_dict:
        error_query_params = python_urlencode({"error": "ไม่พบข้อมูล Batch ที่จะบันทึก กรุณาเริ่มต้นใหม่"})
        return RedirectResponse(url=f"{request.app.url_path_for('ui_show_stock_in_form')}?{error_query_params}", status_code=status.HTTP_303_SEE_OTHER)

    try:
        batch_stock_in_data = BatchStockInSchema.model_validate(batch_data_dict)
        # The service function record_batch_stock_in prepares transactions but doesn't commit.
        inventory_service.record_batch_stock_in(db=db, batch_data=batch_stock_in_data)
        db.commit() # Commit all prepared changes here
        success_message = f"บันทึกการรับสินค้าเข้า Batch (จำนวน {len(batch_stock_in_data.items)} ประเภทสินค้า) เรียบร้อยแล้ว"
        redirect_url_path = str(request.app.url_path_for('ui_view_inventory_summary'))
        query_params = python_urlencode({"message": success_message})
        return RedirectResponse(url=f"{redirect_url_path}?{query_params}", status_code=status.HTTP_303_SEE_OTHER)
    
    except ValueError as e:
        db.rollback()
        request.session["batch_stock_in_data"] = batch_data_dict # Put data back for retry
        error_query_params = python_urlencode({"error": str(e)})
        review_page_url = str(request.app.url_path_for('ui_show_stock_in_review_page'))
        return RedirectResponse(url=f"{review_page_url}?{error_query_params}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        db.rollback()
        request.session["batch_stock_in_data"] = batch_data_dict 
        print(f"Unexpected error confirming batch stock-in: {type(e).__name__} - {e}")
        error_query_params = python_urlencode({"error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึก Batch สต็อกเข้า"})
        review_page_url = str(request.app.url_path_for('ui_show_stock_in_review_page'))
        return RedirectResponse(url=f"{review_page_url}?{error_query_params}", status_code=status.HTTP_303_SEE_OTHER)


# --- Adjustment Routes (No changes from previous versions you provided) ---
@ui_router.get("/adjust/", response_class=HTMLResponse, name="ui_show_adjustment_form")
async def ui_show_adjustment_form(request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
    categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
    adjustment_reasons = [ "สินค้าเสียหาย", "สินค้าหมดอายุ", "แก้ไขยอดจากการนับสต็อก - เพิ่ม", "แก้ไขยอดจากการนับสต็อก - ลด", "ใช้ภายใน", "ส่งคืนผู้ขาย", "อื่นๆ" ]
    return templates.TemplateResponse("inventory/adjustment.html", {
        "request": request, "categories": categories, "locations": locations,
        "reasons": adjustment_reasons, "form_data": None, "error": None })

@ui_router.post("/adjust/", response_class=HTMLResponse, name="ui_handle_adjustment_form")
async def ui_handle_adjustment_form(
    request: Request, db: Session = Depends(get_db), product_id: int = Form(...), location_id: int = Form(...),
    quantity_change: float = Form(...), reason: Optional[str] = Form(None), notes: Optional[str] = Form(None),
    sku_barcode_display_only: Optional[str] = Form(None), category_id_for_reload: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = {"product_id": product_id, "location_id": location_id, "quantity_change": quantity_change,
                      "reason": reason, "notes": notes, "sku_barcode_display_only": sku_barcode_display_only,
                      "category_id_for_reload": category_id_for_reload}
    adjustment_reasons = [ "สินค้าเสียหาย", "สินค้าหมดอายุ", "แก้ไขยอดจากการนับสต็อก - เพิ่ม", "แก้ไขยอดจากการนับสต็อก - ลด", "ใช้ภายใน", "ส่งคืนผู้ขาย", "อื่นๆ" ]
    common_context = {"request": request,
                            "locations": location_service.get_locations(db=db, limit=1000).get("items", []),
                            "categories": category_service.get_categories(db=db, limit=1000).get("items", []),
                            "reasons": adjustment_reasons, "form_data": form_data_dict}
    if not product_id:
        common_context["error"] = "ไม่พบรหัสสินค้า กรุณาค้นหาหรือเลือกสินค้าอีกครั้ง"
        return templates.TemplateResponse("inventory/adjustment.html", common_context, status_code=status.HTTP_400_BAD_REQUEST)
    if quantity_change == 0:
         common_context["error"] = "จำนวนที่เปลี่ยนแปลงต้องไม่เป็นศูนย์"
         return templates.TemplateResponse("inventory/adjustment.html", common_context, status_code=status.HTTP_400_BAD_REQUEST)
    try:
        schema_data = {
            "product_id": product_id,
            "location_id": location_id,
            "quantity_change": quantity_change,
            "reason": reason,
            "notes": notes
        }
        adjustment_data_schema = schemas.StockAdjustmentSchema(**schema_data) #
        inventory_service.record_stock_adjustment(db=db, adjustment_data=adjustment_data_schema)
        db.commit() 
        success_message = f"บันทึกการปรับปรุงสต็อก (สินค้า ID: {product_id}, สถานที่ ID: {location_id}, จำนวน: {quantity_change:+}) เรียบร้อยแล้ว"
        redirect_url_path = str(request.app.url_path_for('ui_view_inventory_summary'))
        query_params = python_urlencode({"message": success_message})
        return RedirectResponse(url=f"{redirect_url_path}?{query_params}" if query_params else redirect_url_path, status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
         db.rollback()
         common_context["error"] = str(e)
         return templates.TemplateResponse("inventory/adjustment.html", common_context, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         db.rollback()
         print(f"Unexpected adjustment form error: {type(e).__name__} - {e}")
         common_context["error"] = "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึกการปรับปรุงสต็อก"
         return templates.TemplateResponse("inventory/adjustment.html", common_context, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --- Transfer Routes (No changes from previous versions you provided) ---
@ui_router.get("/transfer/", response_class=HTMLResponse, name="ui_show_transfer_form")
async def ui_show_transfer_form(request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
    categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
    return templates.TemplateResponse("inventory/transfer.html", {"request": request, "locations": locations, "categories": categories, "form_data": None, "error": None})

@ui_router.post("/transfer/", response_class=HTMLResponse, name="ui_handle_transfer_form")
async def ui_handle_transfer_form(
    request: Request, db: Session = Depends(get_db), product_id: int = Form(...),
    from_location_id: int = Form(...), to_location_id: int = Form(...),
    quantity: float = Form(...), notes: Optional[str] = Form(None), 
    sku_barcode_display_only: Optional[str] = Form(None), category_id_for_reload: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = {"product_id": product_id, "from_location_id": from_location_id, "to_location_id": to_location_id,
                      "quantity": quantity, "notes": notes, "sku_barcode_display_only": sku_barcode_display_only,
                      "category_id_for_reload": category_id_for_reload}
    common_context = {"request": request, "locations": location_service.get_locations(db=db, limit=1000).get("items", []),
                            "categories": category_service.get_categories(db=db, limit=1000).get("items", []),
                            "form_data": form_data_dict}
    if not product_id:
        common_context["error"] = "ไม่พบรหัสสินค้า กรุณาค้นหาหรือเลือกสินค้าอีกครั้ง"
        return templates.TemplateResponse("inventory/transfer.html", common_context, status_code=status.HTTP_400_BAD_REQUEST)
    if from_location_id == to_location_id:
        common_context["error"] = "สถานที่จัดเก็บต้นทางและปลายทางต้องแตกต่างกัน"
        return templates.TemplateResponse("inventory/transfer.html", common_context, status_code=status.HTTP_400_BAD_REQUEST)
    try:
        schema_data = {
            "product_id": product_id,
            "from_location_id": from_location_id,
            "to_location_id": to_location_id,
            "quantity": quantity,
            "notes": notes
        }
        transfer_data_schema = schemas.StockTransferSchema(**schema_data) #
        inventory_service.record_stock_transfer(db=db, transfer_data=transfer_data_schema)
        db.commit() 
        success_message = f"โอนย้ายสินค้า ID {product_id} จำนวน {quantity} จากสถานที่ ID {from_location_id} ไปยัง ID {to_location_id} เรียบร้อยแล้ว"
        redirect_url_path = str(request.app.url_path_for('ui_view_inventory_summary'))
        query_params = python_urlencode({"message": success_message})
        return RedirectResponse(url=f"{redirect_url_path}?{query_params}" if query_params else redirect_url_path, status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
         db.rollback()
         common_context["error"] = str(e)
         return templates.TemplateResponse("inventory/transfer.html", common_context, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         db.rollback()
         print(f"Unexpected transfer form error: {type(e).__name__} - {e}")
         common_context["error"] = "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึกการโอนย้าย"
         return templates.TemplateResponse("inventory/transfer.html", common_context, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --- Transaction Log Page Route (No changes from previous versions you provided) ---
@ui_router.get("/transactions/", response_class=HTMLResponse, name="ui_view_all_transactions")
async def ui_view_all_transactions(
    request: Request, page: int = Query(1, ge=1), limit: int = Query(30, ge=1, le=200),
    product_id_str: Optional[str] = Query(None, alias="product_id"), location_id_str: Optional[str] = Query(None, alias="location_id"),
    type_str: Optional[str] = Query(None, alias="type"), start_date_str: Optional[str] = Query(None, alias="start_date"),
    end_date_str: Optional[str] = Query(None, alias="end_date"), db: Session = Depends(get_db)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    skip = (page - 1) * limit; skip = max(0, skip); parse_error = None
    product_id: Optional[int] = None; location_id: Optional[int] = None; transaction_type: Optional[TransactionType] = None
    start_date_obj: Optional[date] = None; end_date_obj: Optional[date] = None
    if product_id_str and product_id_str.isdigit(): product_id = int(product_id_str)
    if location_id_str and location_id_str.isdigit(): location_id = int(location_id_str)
    if type_str and type_str in TransactionType.__members__: transaction_type = TransactionType[type_str]
    elif type_str: parse_error = f"ประเภท Transaction ไม่ถูกต้อง: '{type_str}'"
    try: start_date_obj = date.fromisoformat(start_date_str) if start_date_str and start_date_str.strip() else None
    except ValueError: parse_error = (f"{parse_error}; " if parse_error else "") + f"รูปแบบวันที่เริ่มต้นไม่ถูกต้อง: '{start_date_str}'"
    try: end_date_obj = date.fromisoformat(end_date_str) if end_date_str and end_date_str.strip() else None
    except ValueError: parse_error = (f"{parse_error}; " if parse_error else "") + f"รูปแบบวันที่สิ้นสุดไม่ถูกต้อง: '{end_date_str}'"

    context = {"request": request, "transactions": [], "page": page, "limit": limit, "total_count": 0, "total_pages": 0, "skip": skip,
               "all_products": [], "all_locations": [], "all_transaction_types": TransactionType, 
               "selected_product_id": product_id, "selected_location_id": location_id, "selected_type": type_str,
               "start_date": start_date_str or "", "end_date": end_date_str or "", "error": parse_error,
               "message": request.query_params.get('message'), "models": models, "timedelta": timedelta} # Pass timedelta
    try: context["all_products"] = product_service.get_products(db, limit=10000).get("items", [])
    except Exception as e: print(f"Error fetching products for filter: {e}")
    try: context["all_locations"] = location_service.get_locations(db, limit=1000).get("items", [])
    except Exception as e: print(f"Error fetching locations for filter: {e}")

    if not parse_error:
        try:
            transactions_data = inventory_service.get_inventory_transactions(
                db, skip=skip, limit=limit, product_id=product_id, location_id=location_id,
                transaction_type=transaction_type, start_date=start_date_obj, end_date=end_date_obj
            )
            items_orm = transactions_data.get("items", [])
            total_count = transactions_data.get("total_count", 0)
            formatted_items = []
            for tx_orm in items_orm:
                try:
                    tx_dict = {"id": tx_orm.id, "transaction_type_value": tx_orm.transaction_type.value,
                               "quantity_change": tx_orm.quantity_change, "notes": tx_orm.notes,
                               "cost_per_unit": tx_orm.cost_per_unit, "related_transaction_id": tx_orm.related_transaction_id,
                               'product_name': tx_orm.product.name if tx_orm.product else 'N/A',
                               'product_sku': tx_orm.product.sku if tx_orm.product else 'N/A',
                               'location_name': tx_orm.location.name if tx_orm.location else 'N/A',
                               'transaction_date_formatted': format_thai_datetime(tx_orm.transaction_date, format_str='%d/%m/%y %H:%M'),
                               'production_date_formatted': format_thai_date(tx_orm.production_date, format_str="%d/%m/%Y"),
                               'expiry_date_formatted': format_thai_date(tx_orm.expiry_date, format_str="%d/%m/%Y")}
                    formatted_items.append(tx_dict)
                except Exception as format_err: print(f"Error processing transaction ID {getattr(tx_orm, 'id', 'N/A')} for display: {format_err}")
            context["transactions"] = formatted_items
            context["total_count"] = total_count
            context["total_pages"] = math.ceil(total_count / limit) if limit > 0 else 0
        except Exception as e:
            print(f"Error fetching inventory transactions: {e}")
            context["error"] = f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}"
    return templates.TemplateResponse("inventory/transactions_list.html", context)

# --- Near Expiry Report (No changes from previous versions you provided) ---
@ui_router.get("/near-expiry/", response_class=HTMLResponse, name="ui_near_expiry_report")
async def ui_near_expiry_report(
    request: Request, db: Session = Depends(get_db),
    days_ahead: int = Query(30, ge=1), page: int = Query(1, ge=1), limit: int = Query(15, ge=1)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    skip = (page - 1) * limit; skip = max(0, skip)
    report_data = inventory_service.get_near_expiry_transactions(db, days_ahead=days_ahead, skip=skip, limit=limit)
    transactions_orm = report_data.get("transactions", [])
    total_count = report_data.get("total_count", 0)
    total_pages = math.ceil(total_count / limit) if limit > 0 else 0
    today_date_obj = date.today()
    formatted_transactions = []
    for tx_orm in transactions_orm:
        try:
            tx_dict = {"id": tx_orm.id, "quantity_change": tx_orm.quantity_change, "cost_per_unit": tx_orm.cost_per_unit,
                       "notes": tx_orm.notes, 'product_name': tx_orm.product.name if tx_orm.product else 'N/A',
                       'product_sku': tx_orm.product.sku if tx_orm.product else 'N/A',
                       'location_name': tx_orm.location.name if tx_orm.location else 'N/A',
                       'shelf_life_days': tx_orm.product.shelf_life_days if tx_orm.product and tx_orm.product.shelf_life_days is not None else '-',
                       'expiry_date_formatted': format_thai_date(tx_orm.expiry_date, format_str="%d/%m/%Y"),
                       'transaction_date_formatted': format_thai_datetime(tx_orm.transaction_date, format_str='%d/%m/%y %H:%M'),
                       'days_left': (tx_orm.expiry_date - today_date_obj).days if tx_orm.expiry_date else -1}
            formatted_transactions.append(tx_dict)
        except Exception as format_err: print(f"Error processing near-expiry transaction {getattr(tx_orm, 'id', 'N/A')}: {format_err}")
    context = {"request": request, "transactions": formatted_transactions, "days_ahead": days_ahead, "page": page,
               "limit": limit, "total_count": total_count, "total_pages": total_pages, "today": today_date_obj, "skip": skip,
               "timedelta": timedelta} # Pass timedelta
    return templates.TemplateResponse("reports/near_expiry.html", context)