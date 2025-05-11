# routers/ui/inventory.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import date, timedelta, datetime, time
from urllib.parse import urlencode as python_urlencode
import math

import schemas
import models
from models import TransactionType
from services import inventory_service, product_service, category_service, location_service
from database import get_db

# *** Import time formatting helpers from utils.py ***
try:
    from utils import format_thai_datetime, format_thai_date # <<< แก้ไขตรงนี้
except ImportError:
    # Fallback functions (ควรจะลบออกถ้ามั่นใจว่า utils.py import ได้)
    def format_thai_datetime(value, format_str="%d/%m/%Y %H:%M"): return str(value) if value else '-'
    def format_thai_date(value, format_str="%d/%m/%Y"): return str(value) if value else '-'
    print("Warning: Could not import time formatting functions from utils.py. Using fallback.")

ui_router = APIRouter(
    prefix="/ui/inventory",
    tags=["UI - สต็อกสินค้า"],
    include_in_schema=False
)

# --- ui_view_inventory_summary (เหมือนเดิมจากที่คุณให้มาล่าสุด) ---
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

# --- ui_show_stock_in_form (แก้ไขแล้วสำหรับ SKU input + Category Card) ---
@ui_router.get("/stock-in", response_class=HTMLResponse, name="ui_show_stock_in_form")
async def ui_show_stock_in_form(request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
    categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])

    # Try to get form_data and error from session if using PRG pattern
    # Otherwise, they will be None, which is fine for the first load
    form_data = request.session.pop("form_data", None) if hasattr(request, "session") else None
    error_message = request.session.pop("error_message", None) if hasattr(request, "session") else None


    return templates.TemplateResponse(
        "inventory/stock_in.html",
        {
            "request": request,
            "locations": locations,
            "categories": categories,
            "form_data": form_data,
            "error": error_message
        }
    )

# --- ui_handle_stock_in_form (แก้ไขแล้วสำหรับ SKU input + Category Card) ---
@ui_router.post("/stock-in", response_class=HTMLResponse, name="ui_handle_stock_in_form")
async def ui_handle_stock_in_form(
    request: Request, db: Session = Depends(get_db),
    product_id: int = Form(...),
    location_id: int = Form(...),
    quantity: int = Form(...),
    sku_barcode_display_only: Optional[str] = Form(None),
    category_id_for_reload: Optional[str] = Form(None), # For re-rendering category dropdown
    product_shelf_life: Optional[str] = Form(None),
    cost_per_unit_str: Optional[str] = Form(None, alias="cost_per_unit"),
    production_date_str: Optional[str] = Form(None, alias="production_date"),
    expiry_date_str: Optional[str] = Form(None, alias="expiry_date"),
    notes: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")

    form_data_for_rerender = {
        "product_id": product_id, "location_id": location_id, "quantity": quantity,
        "cost_per_unit": cost_per_unit_str, "production_date": production_date_str,
        "expiry_date": expiry_date_str, "notes": notes,
        "sku_barcode_display_only": sku_barcode_display_only,
        "product_shelf_life": product_shelf_life,
        "category_id_for_reload": category_id_for_reload
    }

    cost_per_unit_float: Optional[float] = None
    production_date_obj: Optional[date] = None
    expiry_date_obj: Optional[date] = None
    error_msg: Optional[str] = None

    if not product_id: # This check should ideally be more robust, e.g., if JS fails
        error_msg = "ไม่พบรหัสสินค้า กรุณาค้นหาด้วย SKU/Barcode หรือเลือกจากรายการสินค้า"

    if not error_msg and cost_per_unit_str is not None and cost_per_unit_str.strip() != "":
        try:
            cost_per_unit_float = float(cost_per_unit_str)
            if cost_per_unit_float < 0: raise ValueError("ต้นทุนต่อหน่วยต้องไม่ติดลบ")
        except ValueError: error_msg = "รูปแบบต้นทุนต่อหน่วยไม่ถูกต้อง"
    if not error_msg and production_date_str and production_date_str.strip():
        try: production_date_obj = date.fromisoformat(production_date_str)
        except ValueError: error_msg = "รูปแบบวันที่ผลิตไม่ถูกต้อง (YYYY-MM-DD)"
    if not error_msg and expiry_date_str and expiry_date_str.strip():
        try: expiry_date_obj = date.fromisoformat(expiry_date_str)
        except ValueError: error_msg = "รูปแบบวันที่หมดอายุไม่ถูกต้อง (YYYY-MM-DD)"

    if error_msg:
        locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
        categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
        # If using PRG, store in session and redirect:
        # if hasattr(request, "session"):
        #     request.session["form_data"] = form_data_for_rerender
        #     request.session["error_message"] = error_msg
        # return RedirectResponse(url=request.app.url_path_for('ui_show_stock_in_form'), status_code=status.HTTP_303_SEE_OTHER)
        # Else, render directly (as per current structure)
        return templates.TemplateResponse(
            "inventory/stock_in.html", {
                "request": request, "locations": locations, "categories": categories,
                "error": error_msg, "form_data": form_data_for_rerender
            }, status_code=status.HTTP_400_BAD_REQUEST)

    try:
         stock_in_data = schemas.StockInSchema(
             product_id=product_id, location_id=location_id, quantity=quantity,
             cost_per_unit=cost_per_unit_float, production_date=production_date_obj,
             expiry_date=expiry_date_obj, notes=notes
         )
         inventory_service.record_stock_in(db=db, stock_in_data=stock_in_data)
         success_message = f"บันทึกการรับสินค้าเข้า (รหัสสินค้า: {product_id}, จำนวน: {quantity}) เรียบร้อยแล้ว"
         redirect_url_path = str(request.app.url_path_for('ui_view_inventory_summary'))
         query_params = python_urlencode({"message": success_message})
         redirect_url = f"{redirect_url_path}?{query_params}" if query_params else redirect_url_path
         return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e: # Specific errors from service layer
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         return templates.TemplateResponse(
             "inventory/stock_in.html", {
                 "request": request, "locations": locations, "categories": categories,
                 "error": str(e), "form_data": form_data_for_rerender
             }, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e: # Catch any other unexpected errors
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         print(f"Unexpected stock-in form error: {type(e).__name__} - {e}")
         return templates.TemplateResponse(
             "inventory/stock_in.html", {
                 "request": request, "locations": locations, "categories": categories,
                 "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึกสต็อกเข้า", "form_data": form_data_for_rerender
             }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --- Adjustment Routes ---
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
    quantity_change: int = Form(...), reason: Optional[str] = Form(None), notes: Optional[str] = Form(None),
    sku_barcode_display_only: Optional[str] = Form(None), category_id_for_reload: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = {"product_id": product_id, "location_id": location_id, "quantity_change": quantity_change,
                      "reason": reason, "notes": notes, "sku_barcode_display_only": sku_barcode_display_only,
                      "category_id_for_reload": category_id_for_reload}
    adjustment_reasons = [ "สินค้าเสียหาย", "สินค้าหมดอายุ", "แก้ไขยอดจากการนับสต็อก - เพิ่ม", "แก้ไขยอดจากการนับสต็อก - ลด", "ใช้ภายใน", "ส่งคืนผู้ขาย", "อื่นๆ" ]
    common_error_context = {"request": request,
                            "locations": location_service.get_locations(db=db, limit=1000).get("items", []),
                            "categories": category_service.get_categories(db=db, limit=1000).get("items", []),
                            "reasons": adjustment_reasons, "form_data": form_data_dict}
    if not product_id:
        common_error_context["error"] = "ไม่พบรหัสสินค้า กรุณาค้นหาหรือเลือกสินค้าอีกครั้ง"
        return templates.TemplateResponse("inventory/adjustment.html", common_error_context, status_code=status.HTTP_400_BAD_REQUEST)
    if quantity_change == 0:
         common_error_context["error"] = "จำนวนที่เปลี่ยนแปลงต้องไม่เป็นศูนย์"
         return templates.TemplateResponse("inventory/adjustment.html", common_error_context, status_code=status.HTTP_400_BAD_REQUEST)
    try:
        schema_data = {k: v for k, v in form_data_dict.items() if k in schemas.StockAdjustmentSchema.model_fields}
        adjustment_data_schema = schemas.StockAdjustmentSchema(**schema_data)
        inventory_service.record_stock_adjustment(db=db, adjustment_data=adjustment_data_schema)
        success_message = f"บันทึกการปรับปรุงสต็อก (สินค้า ID: {product_id}, สถานที่ ID: {location_id}, จำนวน: {quantity_change:+}) เรียบร้อยแล้ว"
        redirect_url_path = str(request.app.url_path_for('ui_view_inventory_summary'))
        query_params = python_urlencode({"message": success_message})
        return RedirectResponse(url=f"{redirect_url_path}?{query_params}" if query_params else redirect_url_path, status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
         common_error_context["error"] = str(e)
         return templates.TemplateResponse("inventory/adjustment.html", common_error_context, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         print(f"Unexpected adjustment form error: {type(e).__name__} - {e}")
         common_error_context["error"] = "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึกการปรับปรุงสต็อก"
         return templates.TemplateResponse("inventory/adjustment.html", common_error_context, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --- Near Expiry Report ---
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
               "limit": limit, "total_count": total_count, "total_pages": total_pages, "today": today_date_obj, "skip": skip}
    return templates.TemplateResponse("reports/near_expiry.html", context)

# --- Transfer Routes ---
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
    quantity: int = Form(...), notes: Optional[str] = Form(None),
    sku_barcode_display_only: Optional[str] = Form(None), category_id_for_reload: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = {"product_id": product_id, "from_location_id": from_location_id, "to_location_id": to_location_id,
                      "quantity": quantity, "notes": notes, "sku_barcode_display_only": sku_barcode_display_only,
                      "category_id_for_reload": category_id_for_reload}
    common_error_context = {"request": request, "locations": location_service.get_locations(db=db, limit=1000).get("items", []),
                            "categories": category_service.get_categories(db=db, limit=1000).get("items", []),
                            "form_data": form_data_dict}
    if not product_id:
        common_error_context["error"] = "ไม่พบรหัสสินค้า กรุณาค้นหาหรือเลือกสินค้าอีกครั้ง"
        return templates.TemplateResponse("inventory/transfer.html", common_error_context, status_code=status.HTTP_400_BAD_REQUEST)
    if from_location_id == to_location_id:
        common_error_context["error"] = "สถานที่จัดเก็บต้นทางและปลายทางต้องแตกต่างกัน"
        return templates.TemplateResponse("inventory/transfer.html", common_error_context, status_code=status.HTTP_400_BAD_REQUEST)
    try:
        schema_data = {k:v for k,v in form_data_dict.items() if k in schemas.StockTransferSchema.model_fields}
        transfer_data_schema = schemas.StockTransferSchema(**schema_data)
        inventory_service.record_stock_transfer(db=db, transfer_data=transfer_data_schema)
        success_message = f"โอนย้ายสินค้า ID {product_id} จำนวน {quantity} จากสถานที่ ID {from_location_id} ไปยัง ID {to_location_id} เรียบร้อยแล้ว"
        redirect_url_path = str(request.app.url_path_for('ui_view_inventory_summary'))
        query_params = python_urlencode({"message": success_message})
        return RedirectResponse(url=f"{redirect_url_path}?{query_params}" if query_params else redirect_url_path, status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
         common_error_context["error"] = str(e)
         return templates.TemplateResponse("inventory/transfer.html", common_error_context, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         print(f"Unexpected transfer form error: {type(e).__name__} - {e}")
         common_error_context["error"] = "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึกการโอนย้าย"
         return templates.TemplateResponse("inventory/transfer.html", common_error_context, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --- Transaction Log Page Route ---
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
               "message": request.query_params.get('message'), "models": models}
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