# routers/ui/inventory.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import date, timedelta, datetime, time # เพิ่ม datetime, time
from urllib.parse import urlencode as python_urlencode
import math

# Adjust imports based on your project structure
import schemas
import models
from models import TransactionType # Import Enum for filtering
from services import inventory_service, product_service, category_service, location_service
from database import get_db

# Import time formatting helpers (assuming they are in main or utils)
try:
    # หากย้าย function ไปไว้ที่ utils.py ก็แก้ path ตรงนี้
    from main import format_thai_datetime, format_thai_date
except ImportError:
    # Fallback functions (เผื่อกรณี import ไม่ได้ แต่ไม่แนะนำสำหรับ Production)
    def format_thai_datetime(value, format="%d/%m/%Y %H:%M"): return str(value) if value else '-'
    def format_thai_date(value, format="%d/%m/%Y"): return str(value) if value else '-'
    print("Warning: Could not import time formatting functions from main.py. Using fallback.")

# Define prefix here
ui_router = APIRouter(
    prefix="/ui/inventory",
    tags=["UI - สต็อกสินค้า"],
    include_in_schema=False
)

# --- UI Routes ---
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
    items = report_data.get("items", [])
    total_count = report_data.get("total_count", 0)
    total_pages = math.ceil(total_count / limit) if limit > 0 else 0
    categories_data = category_service.get_categories(db=db, limit=1000); all_categories = categories_data.get("items", [])
    locations_data = location_service.get_locations(db=db, limit=1000); all_locations = locations_data.get("items", [])

    # --- Format time for display ---
    formatted_items = []
    for item in items:
        # Validate using Pydantic before accessing attributes
        try:
            validated_item = schemas.CurrentStock.model_validate(item)
            item_dict = validated_item.model_dump() # Convert validated item to dict
            item_dict['last_updated_formatted'] = format_thai_datetime(validated_item.last_updated, format='%d/%m/%y %H:%M')
            # Add shelf life display (handle potential None product)
            item_dict['product'] = {} # Ensure product dict exists
            if validated_item.product:
                item_dict['product']['id'] = validated_item.product.id
                item_dict['product']['name'] = validated_item.product.name
                item_dict['product']['sku'] = validated_item.product.sku
                item_dict['product']['shelf_life_display'] = validated_item.product.shelf_life_days if validated_item.product.shelf_life_days is not None else '-'
                if validated_item.product.category:
                     item_dict['product']['category'] = {"name": validated_item.product.category.name}
            if validated_item.location:
                item_dict['location'] = {"name": validated_item.location.name}
            formatted_items.append(item_dict)
        except Exception as e:
            print(f"Error processing stock item for display: {e}")
            # Optionally skip item or add placeholder

    # ----------------------------------------------------

    context = {
        "request": request, "stock_summary": formatted_items, # <-- Use formatted items
        "page": page, "limit": limit, "total_count": total_count, "total_pages": total_pages,
        "message": request.query_params.get('message'), "error": request.query_params.get('error'),
        "skip": skip, "all_categories": all_categories, "selected_category_id": category_id,
        "all_locations": all_locations, "selected_location_id": location_id
        # create_filter_link will use the global helper registered in main.py
    }
    return templates.TemplateResponse("inventory/summary.html", context)


@ui_router.get("/stock-in", response_class=HTMLResponse, name="ui_show_stock_in_form")
async def ui_show_stock_in_form(request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
    categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
    return templates.TemplateResponse("inventory/stock_in.html", {"request": request, "categories": categories, "locations": locations, "form_data": None, "error": None})


@ui_router.post("/stock-in", response_class=HTMLResponse, name="ui_handle_stock_in_form")
async def ui_handle_stock_in_form(
    request: Request, db: Session = Depends(get_db),
    product_id: int = Form(...), location_id: int = Form(...), quantity: int = Form(...),
    cost_per_unit_str: Optional[str] = Form(None, alias="cost_per_unit"),
    production_date_str: Optional[str] = Form(None, alias="production_date"),
    expiry_date_str: Optional[str] = Form(None, alias="expiry_date"),
    notes: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = { # Store raw form data for re-rendering on error
        "product_id": product_id, "location_id": location_id, "quantity": quantity,
        "cost_per_unit": cost_per_unit_str, "production_date": production_date_str,
        "expiry_date": expiry_date_str, "notes": notes,
    }
    cost_per_unit_float: Optional[float] = None; production_date_obj: Optional[date] = None; expiry_date_obj: Optional[date] = None
    error_msg: Optional[str] = None

    # Validate Cost
    if cost_per_unit_str is not None and cost_per_unit_str.strip() != "":
        try:
            cost_per_unit_float = float(cost_per_unit_str)
            if cost_per_unit_float < 0: raise ValueError("ต้นทุนต่อหน่วยต้องไม่ติดลบ")
        except ValueError: error_msg = "รูปแบบต้นทุนต่อหน่วยไม่ถูกต้อง"
    # Validate Production Date
    if not error_msg and production_date_str and production_date_str.strip():
        try: production_date_obj = date.fromisoformat(production_date_str)
        except ValueError: error_msg = "รูปแบบวันที่ผลิตไม่ถูกต้อง (YYYY-MM-DD)"
    # Validate Expiry Date
    if not error_msg and expiry_date_str and expiry_date_str.strip():
        try: expiry_date_obj = date.fromisoformat(expiry_date_str)
        except ValueError: error_msg = "รูปแบบวันที่หมดอายุไม่ถูกต้อง (YYYY-MM-DD)"

    # If validation failed, re-render form with error
    if error_msg:
        locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
        categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
        # Fetch product category if product_id is known for pre-selection
        if product_id:
            prod = product_service.get_product(db, product_id=product_id)
            if prod: form_data_dict['category_id'] = prod.category_id
        return templates.TemplateResponse("inventory/stock_in.html", {"request": request, "categories": categories, "locations": locations, "error": error_msg, "form_data": form_data_dict}, status_code=status.HTTP_400_BAD_REQUEST)

    # Proceed if validation passed
    try:
         stock_in_data = schemas.StockInSchema(
             product_id=product_id, location_id=location_id, quantity=quantity,
             cost_per_unit=cost_per_unit_float, production_date=production_date_obj,
             expiry_date=expiry_date_obj, notes=notes
         )
         inventory_service.record_stock_in(db=db, stock_in_data=stock_in_data)
         success_message = f"บันทึกการรับสินค้าเข้า (รหัสสินค้า: {product_id}, จำนวน: {quantity}) เรียบร้อยแล้ว"
         redirect_url = "/ui/inventory/summary/" # Fallback
         try:
             redirect_url_path = str(request.app.url_path_for('ui_view_inventory_summary'))
             query_params = python_urlencode({"message": success_message})
             redirect_url = f"{redirect_url_path}?{query_params}" if query_params else redirect_url_path
         except Exception as redirect_err: print(f"Error creating redirect URL: {redirect_err}")
         return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e: # Catch errors from service
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         if product_id:
            prod = product_service.get_product(db, product_id=product_id)
            if prod: form_data_dict['category_id'] = prod.category_id
         return templates.TemplateResponse("inventory/stock_in.html", {"request": request, "categories": categories, "locations": locations, "error": str(e), "form_data": form_data_dict}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e: # Catch unexpected errors
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         print(f"Unexpected stock-in form error: {type(e).__name__} - {e}")
         if product_id:
            prod = product_service.get_product(db, product_id=product_id)
            if prod: form_data_dict['category_id'] = prod.category_id
         return templates.TemplateResponse("inventory/stock_in.html", {"request": request, "categories": categories, "locations": locations, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึกสต็อกเข้า", "form_data": form_data_dict}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@ui_router.get("/adjust/", response_class=HTMLResponse, name="ui_show_adjustment_form")
async def ui_show_adjustment_form(request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
    categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
    adjustment_reasons = [ "สินค้าเสียหาย", "สินค้าหมดอายุ", "แก้ไขยอดจากการนับสต็อก - เพิ่ม", "แก้ไขยอดจากการนับสต็อก - ลด", "ใช้ภายใน", "ส่งคืนผู้ขาย", "อื่นๆ" ]
    return templates.TemplateResponse("inventory/adjustment.html", { "request": request, "categories": categories, "locations": locations, "reasons": adjustment_reasons, "form_data": None, "error": None })

@ui_router.post("/adjust/", response_class=HTMLResponse, name="ui_handle_adjustment_form")
async def ui_handle_adjustment_form(
    request: Request, db: Session = Depends(get_db), product_id: int = Form(...), location_id: int = Form(...),
    quantity_change: int = Form(...), reason: Optional[str] = Form(None), notes: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = { "product_id": product_id, "location_id": location_id, "quantity_change": quantity_change, "reason": reason, "notes": notes }
    adjustment_reasons = [ "สินค้าเสียหาย", "สินค้าหมดอายุ", "แก้ไขยอดจากการนับสต็อก - เพิ่ม", "แก้ไขยอดจากการนับสต็อก - ลด", "ใช้ภายใน", "ส่งคืนผู้ขาย", "อื่นๆ" ]
    if quantity_change == 0:
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         return templates.TemplateResponse("inventory/adjustment.html", {"request": request, "categories": categories, "locations": locations, "reasons": adjustment_reasons, "error": "จำนวนที่เปลี่ยนแปลงต้องไม่เป็นศูนย์", "form_data": form_data_dict }, status_code=status.HTTP_400_BAD_REQUEST)
    try:
        adjustment_data_schema = schemas.StockAdjustmentSchema(**form_data_dict)
        inventory_service.record_stock_adjustment(db=db, adjustment_data=adjustment_data_schema)
        success_message = f"บันทึกการปรับปรุงสต็อก (สินค้า ID: {product_id}, สถานที่ ID: {location_id}, จำนวน: {quantity_change:+}) เรียบร้อยแล้ว"
        redirect_url = "/ui/inventory/summary/" # Fallback
        try:
            redirect_url_path = str(request.app.url_path_for('ui_view_inventory_summary'))
            query_params = python_urlencode({"message": success_message})
            redirect_url = f"{redirect_url_path}?{query_params}" if query_params else redirect_url_path
        except Exception as redirect_err: print(f"Error creating redirect URL: {redirect_err}")
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         if product_id:
             prod = product_service.get_product(db, product_id=product_id)
             if prod: form_data_dict['category_id'] = prod.category_id # Add category for potential re-render
         return templates.TemplateResponse("inventory/adjustment.html", {"request": request, "categories": categories, "locations": locations, "reasons": adjustment_reasons, "error": str(e), "form_data": form_data_dict}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         print(f"Unexpected adjustment form error: {type(e).__name__} - {e}")
         if product_id:
             prod = product_service.get_product(db, product_id=product_id)
             if prod: form_data_dict['category_id'] = prod.category_id
         return templates.TemplateResponse("inventory/adjustment.html", {"request": request, "categories": categories, "locations": locations, "reasons": adjustment_reasons, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึกการปรับปรุงสต็อก", "form_data": form_data_dict}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@ui_router.get("/near-expiry/", response_class=HTMLResponse, name="ui_near_expiry_report")
async def ui_near_expiry_report(
    request: Request, db: Session = Depends(get_db),
    days_ahead: int = Query(30, ge=1), page: int = Query(1, ge=1), limit: int = Query(15, ge=1)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    skip = (page - 1) * limit; skip = max(0, skip)
    report_data = inventory_service.get_near_expiry_transactions(db, days_ahead=days_ahead, skip=skip, limit=limit)
    transactions = report_data.get("transactions", [])
    total_count = report_data.get("total_count", 0)
    total_pages = math.ceil(total_count / limit) if limit > 0 else 0
    today_date_obj = date.today()

    # --- Format time and add calculated fields ---
    formatted_transactions = []
    for tx in transactions:
        try:
            tx_dict = schemas.InventoryTransaction.model_validate(tx).model_dump(exclude={'product','location'})
            tx_dict['product_name'] = tx.product.name if tx.product else 'N/A'
            tx_dict['product_sku'] = tx.product.sku if tx.product else 'N/A'
            tx_dict['location_name'] = tx.location.name if tx.location else 'N/A'
            tx_dict['shelf_life_days'] = tx.product.shelf_life_days if tx.product and tx.product.shelf_life_days is not None else '-'
            tx_dict['expiry_date_formatted'] = format_thai_date(tx.expiry_date) # Format Date
            tx_dict['transaction_date_formatted'] = format_thai_datetime(tx.transaction_date, format='%d/%m/%y %H:%M') # Format DateTime
            tx_dict['days_left'] = (tx.expiry_date - today_date_obj).days if tx.expiry_date else -1
            formatted_transactions.append(tx_dict)
        except Exception as format_err:
            print(f"Error processing near-expiry transaction {tx.id}: {format_err}")
    # --------------------------------------------

    context = {
        "request": request, "transactions": formatted_transactions,
        "days_ahead": days_ahead, "page": page, "limit": limit, "total_count": total_count,
        "total_pages": total_pages, "today": today_date_obj,
        "skip": skip
    }
    return templates.TemplateResponse("reports/near_expiry.html", context)

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
    quantity: int = Form(...), notes: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = { "product_id": product_id, "from_location_id": from_location_id, "to_location_id": to_location_id, "quantity": quantity, "notes": notes }
    if from_location_id == to_location_id:
        error = "สถานที่จัดเก็บต้นทางและปลายทางต้องแตกต่างกัน"
        locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
        categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
        return templates.TemplateResponse("inventory/transfer.html", {"request": request, "locations": locations, "categories": categories, "form_data": form_data_dict, "error": error }, status_code=status.HTTP_400_BAD_REQUEST)
    try:
        transfer_data_schema = schemas.StockTransferSchema(**form_data_dict)
        inventory_service.record_stock_transfer(db=db, transfer_data=transfer_data_schema)
        success_message = f"โอนย้ายสินค้า ID {product_id} จำนวน {quantity} จากสถานที่ ID {from_location_id} ไปยัง ID {to_location_id} เรียบร้อยแล้ว"
        redirect_url = "/ui/inventory/summary/" # Fallback
        try:
             redirect_url_path = str(request.app.url_path_for('ui_view_inventory_summary'))
             query_params = python_urlencode({"message": success_message})
             redirect_url = f"{redirect_url_path}?{query_params}" if query_params else redirect_url_path
        except Exception as redirect_err: print(f"Error creating redirect URL: {redirect_err}")
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         if product_id:
             prod = product_service.get_product(db, product_id=product_id)
             if prod: form_data_dict['category_id'] = prod.category_id
         return templates.TemplateResponse("inventory/transfer.html", { "request": request, "locations": locations, "categories": categories, "form_data": form_data_dict, "error": str(e) }, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         print(f"Unexpected transfer form error: {type(e).__name__} - {e}")
         if product_id:
             prod = product_service.get_product(db, product_id=product_id)
             if prod: form_data_dict['category_id'] = prod.category_id
         return templates.TemplateResponse("inventory/transfer.html", { "request": request, "locations": locations, "categories": categories, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึกการโอนย้าย", "form_data": form_data_dict }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


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

    # --- Validate and Convert Filters ---
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
    # -----------------------------------

    context = { # Initialize context early
        "request": request, "transactions": [], "page": page, "limit": limit, "total_count": 0, "total_pages": 0, "skip": skip,
        "all_products": [], "all_locations": [], "all_transaction_types": TransactionType,
        "selected_product_id": product_id, "selected_location_id": location_id, "selected_type": type_str,
        "start_date": start_date_str or "", "end_date": end_date_str or "", "error": parse_error,
        "message": request.query_params.get('message'),
        "models": models # Pass models module if needed in template
    }

    # Fetch data for filters
    try: context["all_products"] = product_service.get_products(db, limit=10000).get("items", [])
    except Exception as e: print(f"Error fetching products for filter: {e}")
    try: context["all_locations"] = location_service.get_locations(db, limit=1000).get("items", [])
    except Exception as e: print(f"Error fetching locations for filter: {e}")

    # Fetch main transaction data only if no parsing errors
    if not parse_error:
        try:
            transactions_data = inventory_service.get_inventory_transactions(
                db, skip=skip, limit=limit, product_id=product_id, location_id=location_id,
                transaction_type=transaction_type, start_date=start_date_obj, end_date=end_date_obj
            )
            items = transactions_data.get("items", [])
            total_count = transactions_data.get("total_count", 0)

            # *** นี่คือส่วนสำคัญ: การแปลงเวลา ***
            formatted_items = []
            for tx in items:
                try:
                    tx_dict = schemas.InventoryTransaction.model_validate(tx).model_dump(exclude={'product','location'})
                    tx_dict['product_name'] = tx.product.name if tx.product else 'N/A'
                    tx_dict['product_sku'] = tx.product.sku if tx.product else 'N/A'
                    tx_dict['location_name'] = tx.location.name if tx.location else 'N/A'
                    # *** เรียกใช้ Helper Function ที่ import มา ***
                    tx_dict['transaction_date_formatted'] = format_thai_datetime(tx.transaction_date, format='%d/%m/%y %H:%M')
                    tx_dict['production_date_formatted'] = format_thai_date(tx.production_date)
                    tx_dict['expiry_date_formatted'] = format_thai_date(tx.expiry_date)
                    # --------------------------------------------
                    tx_dict['transaction_type_value'] = tx.transaction_type.value
                    formatted_items.append(tx_dict)
                except Exception as format_err:
                    print(f"Error processing transaction ID {getattr(tx, 'id', 'N/A')} for display: {format_err}")
            # *****************************************

            context["transactions"] = formatted_items # <-- ส่ง List ที่ Format แล้ว
            context["total_count"] = total_count
            context["total_pages"] = math.ceil(total_count / limit) if limit > 0 else 0
        except Exception as e:
            print(f"Error fetching inventory transactions: {e}")
            context["error"] = f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}"

    # Render the template
    return templates.TemplateResponse("inventory/transactions_list.html", context)
# --- *** สิ้นสุด Route ใหม่ *** ---