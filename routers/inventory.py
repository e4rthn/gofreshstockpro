# routers/inventory.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Tuple, Dict, Any # Added Dict, Any
from datetime import date, timedelta
from urllib.parse import urlencode as python_urlencode # Renamed to avoid conflict with Jinja's urlencode
import math

# Absolute Imports
import schemas
import models
from services import inventory_service, product_service, category_service, location_service
from database import get_db
# templates access via request.app.state.templates

API_INCLUDE_IN_SCHEMA = True

router = APIRouter(
    # prefix="/api/inventory", # Prefix is set in main.py when including the router
    tags=["API - สต็อกสินค้า"],
    include_in_schema=API_INCLUDE_IN_SCHEMA
)

ui_router = APIRouter(
    prefix="/ui/inventory", # Prefix for UI Routes of Inventory
    tags=["หน้าเว็บ - สต็อกสินค้า"],
    include_in_schema=False
)

# --- API Routes ---
@router.get("/summary/", response_model=List[schemas.CurrentStock])
async def api_get_inventory_summary(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    category_id_str: Optional[str] = Query(None, alias="category_id"),
    location_id_str: Optional[str] = Query(None, alias="location_id"),
    db: Session = Depends(get_db)
):
    category_id: Optional[int] = None
    if category_id_str is not None and category_id_str.strip():
        try:
            category_id = int(category_id_str)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category_id format for API.")

    location_id: Optional[int] = None
    if location_id_str is not None and location_id_str.strip():
        try:
            location_id = int(location_id_str)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid location_id format for API.")

    stock_summary_data = inventory_service.get_current_stock_summary(
        db, skip=skip, limit=limit, category_id=category_id, location_id=location_id
    )
    # Ensure the response matches the List[schemas.CurrentStock] model
    # This might require converting the model objects to the schema if not done automatically
    # For now, assuming the service returns compatible data or FastAPI handles it
    return stock_summary_data.get("items", []) # Return only the items list

@router.post("/stock-in/", response_model=schemas.InventoryTransaction)
async def api_record_new_stock_in(stock_in: schemas.StockInSchema, db: Session = Depends(get_db)):
    try:
        created_transaction = inventory_service.record_stock_in(db=db, stock_in_data=stock_in)
        # Fetching with joinedload to match the response model expectations
        tx = db.query(models.InventoryTransaction).options(
             joinedload(models.InventoryTransaction.product).joinedload(models.Product.category),
             joinedload(models.InventoryTransaction.location)
         ).filter(models.InventoryTransaction.id == created_transaction.id).first()
        if tx is None:
            raise HTTPException(status_code=500, detail="Could not retrieve the created transaction with details.")
        return tx # Return the full transaction object
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบ" in error_message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        else:
            print(f"Stock-in API Error: {error_message}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ไม่สามารถบันทึกสต็อกเข้า: {error_message}")
    except Exception as e:
        print(f"Unexpected API Error during stock-in: {type(e).__name__} - {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดที่ไม่คาดคิด (API Stock-in)")

@router.post("/adjust/", response_model=schemas.InventoryTransaction, status_code=status.HTTP_201_CREATED)
async def api_record_stock_adjustment(adjustment: schemas.StockAdjustmentSchema, db: Session = Depends(get_db)):
    try:
        created_transaction = inventory_service.record_stock_adjustment(db=db, adjustment_data=adjustment)
        tx = db.query(models.InventoryTransaction).options(
             joinedload(models.InventoryTransaction.product).joinedload(models.Product.category),
             joinedload(models.InventoryTransaction.location)
         ).filter(models.InventoryTransaction.id == created_transaction.id).first()
        if tx is None:
            raise HTTPException(status_code=500, detail="Could not retrieve the created adjustment transaction with details.")
        return tx
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบ" in error_message: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        elif "สต็อกไม่เพียงพอ" in error_message: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        elif "ต้องไม่เป็นศูนย์" in error_message: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        else:
            print(f"Adjustment API Error: {error_message}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ไม่สามารถบันทึกการปรับปรุงสต็อก: {error_message}")
    except Exception as e:
        print(f"Unexpected API Error during adjustment: {type(e).__name__} - {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดที่ไม่คาดคิด (API Adjustment)")

@router.get("/near-expiry/", response_model=List[schemas.InventoryTransaction])
async def api_get_near_expiry_report(
    days_ahead: int = Query(30, ge=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    db: Session = Depends(get_db)
):
    # Ensure the service returns data compatible with InventoryTransaction schema
    report_data = inventory_service.get_near_expiry_transactions(db, days_ahead=days_ahead, skip=skip, limit=limit)
    return report_data.get("transactions", []) # Return the list part

@router.post("/transfer/", response_model=List[schemas.InventoryTransaction], status_code=status.HTTP_201_CREATED)
async def api_record_stock_transfer(
    transfer: schemas.StockTransferSchema, db: Session = Depends(get_db)
):
    try:
        tx_out, tx_in = inventory_service.record_stock_transfer(db=db, transfer_data=transfer)
        # Fetch details to match the response model
        t_out = db.query(models.InventoryTransaction).options(
            joinedload(models.InventoryTransaction.product).joinedload(models.Product.category),
            joinedload(models.InventoryTransaction.location)
        ).filter(models.InventoryTransaction.id == tx_out.id).first()
        t_in = db.query(models.InventoryTransaction).options(
            joinedload(models.InventoryTransaction.product).joinedload(models.Product.category),
            joinedload(models.InventoryTransaction.location)
        ).filter(models.InventoryTransaction.id == tx_in.id).first()

        if not t_out or not t_in:
            # This case indicates a problem fetching the just-created transactions
            raise HTTPException(status_code=500, detail="ไม่สามารถดึงข้อมูล Transaction โอนย้ายที่สร้างได้")
        return [t_out, t_in] # Return list of the detailed transactions
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบ" in error_message: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        elif "สต็อกไม่เพียงพอ" in error_message: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        elif "ต้องแตกต่างกัน" in error_message: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        else:
            print(f"Transfer API Error: {error_message}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ไม่สามารถโอนย้ายสต็อก: {error_message}")
    except Exception as e:
        print(f"Unexpected API Error during transfer: {type(e).__name__} - {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดที่ไม่คาดคิด (API Transfer)")


# --- UI Routes ---
@ui_router.get("/summary/", response_class=HTMLResponse, name="ui_view_inventory_summary")
async def ui_view_inventory_summary(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(15, ge=1),
    category_str: Optional[str] = Query(None, alias="category"),
    location_str: Optional[str] = Query(None, alias="location"),
    db: Session = Depends(get_db)
):
    templates = request.app.state.templates
    if templates is None:
        raise HTTPException(status_code=500, detail="Templates not configured")

    skip = (page - 1) * limit

    category_id: Optional[int] = None
    if category_str is not None and category_str.strip().isdigit():
        category_id = int(category_str)

    location_id: Optional[int] = None
    if location_str is not None and location_str.strip().isdigit():
        location_id = int(location_str)

    report_data = inventory_service.get_current_stock_summary(
        db, skip=skip, limit=limit, category_id=category_id, location_id=location_id
    )
    items = report_data.get("items", [])
    total_count = report_data.get("total_count", 0)
    total_pages = math.ceil(total_count / limit) if limit > 0 else 0

    categories_data = category_service.get_categories(db=db, limit=1000)
    all_categories = categories_data.get("items", [])

    locations_data = location_service.get_locations(db=db, limit=1000)
    all_locations = locations_data.get("items", [])

    base_summary_url_path = str(request.app.url_path_for('ui_view_inventory_summary'))

    # --- Helper function to create filter links for the template ---
    # (This could potentially be moved to a shared utility if used in many places)
    def _create_filter_link_for_template(**kwargs_to_update):
        # Start with current query params from the request
        current_request_params = dict(request.query_params)
        final_query_params = {}

        # Carry over 'limit' unless explicitly changed
        if 'limit' not in kwargs_to_update and 'limit' in current_request_params:
            final_query_params['limit'] = current_request_params['limit']
        elif 'limit' in kwargs_to_update and kwargs_to_update['limit'] is not None:
            final_query_params['limit'] = str(kwargs_to_update['limit'])

        # Handle 'location' and 'category' filters
        for key in ['location', 'category']:
            if key in kwargs_to_update:
                value = kwargs_to_update[key]
                if value is not None and str(value).strip() != "":
                    final_query_params[key] = str(value) # Set/update value
                # If value is None or empty, the key is removed (not added to final_query_params)
            elif key in current_request_params and str(current_request_params[key]).strip() != "":
                final_query_params[key] = current_request_params[key] # Carry over existing value

        # Handle 'page' - reset if filters change, otherwise carry over or set explicitly
        if 'page' in kwargs_to_update:
            if kwargs_to_update['page'] is not None:
                final_query_params['page'] = str(kwargs_to_update['page'])
        elif any(k in kwargs_to_update for k in ['location', 'category']):
             final_query_params['page'] = '1' # Reset page if location/category changed
        elif 'page' in current_request_params:
             final_query_params['page'] = current_request_params['page']
        # If no page info, it defaults based on Query(1, ge=1) or is absent

        query_string = python_urlencode(final_query_params)
        return f"{base_summary_url_path}?{query_string}" if query_string else base_summary_url_path

    context = {
        "request": request, "stock_summary": items, "page": page, "limit": limit,
        "total_count": total_count, "total_pages": total_pages,
        "message": request.query_params.get('message'),
        "error": request.query_params.get('error'),
        "skip": skip,
        "all_categories": all_categories,
        "selected_category_id": category_id,
        "all_locations": all_locations,
        "selected_location_id": location_id,
        "create_filter_link": _create_filter_link_for_template # Pass the helper function
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
    request: Request, db: Session = Depends(get_db), product_id: int = Form(...), location_id: int = Form(...),
    quantity: int = Form(...), cost_per_unit_str: Optional[str] = Form(None, alias="cost_per_unit"),
    expiry_date_str: Optional[str] = Form(None, alias="expiry_date"),
    notes: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")

    form_data_dict = {
        "product_id": product_id, "location_id": location_id, "quantity": quantity,
        "cost_per_unit": cost_per_unit_str, "expiry_date": expiry_date_str, "notes": notes
    }
    cost_per_unit_float: Optional[float] = None
    if cost_per_unit_str is not None and cost_per_unit_str.strip() != "":
        try:
            cost_per_unit_float = float(cost_per_unit_str)
            if cost_per_unit_float < 0: raise ValueError("ต้นทุนต่อหน่วยต้องไม่ติดลบ")
        except ValueError:
             locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
             categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
             # Attempt to fetch category_id from product_id for pre-selection
             product = product_service.get_product(db, product_id=product_id)
             form_data_dict['category_id'] = product.category_id if product else None
             return templates.TemplateResponse("inventory/stock_in.html", {
                 "request": request, "categories": categories, "locations": locations,
                 "error": "รูปแบบต้นทุนต่อหน่วยไม่ถูกต้อง กรุณาใส่ตัวเลข", "form_data": form_data_dict
             }, status_code=status.HTTP_400_BAD_REQUEST)

    expiry_date_obj: Optional[date] = None
    if expiry_date_str and expiry_date_str.strip():
        try:
            expiry_date_obj = date.fromisoformat(expiry_date_str)
        except ValueError:
             locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
             categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
             product = product_service.get_product(db, product_id=product_id)
             form_data_dict['category_id'] = product.category_id if product else None
             return templates.TemplateResponse("inventory/stock_in.html", {
                 "request": request, "categories": categories, "locations": locations,
                 "error": "รูปแบบวันที่หมดอายุไม่ถูกต้อง กรุณาใช้ yyyy-MM-dd", "form_data": form_data_dict
             }, status_code=status.HTTP_400_BAD_REQUEST)

    try:
         stock_in_data = schemas.StockInSchema(
             product_id=product_id, location_id=location_id, quantity=quantity,
             cost_per_unit=cost_per_unit_float, expiry_date=expiry_date_obj, notes=notes
         )
         created_tx = inventory_service.record_stock_in(db=db, stock_in_data=stock_in_data)
         # Fetch product name for success message
         product = product_service.get_product(db, product_id=product_id)
         product_name = product.name if product else f"ID {product_id}"
         success_message = f"บันทึกการรับ '{product_name}' เข้า (จำนวน: {quantity}) เรียบร้อยแล้ว (Tx ID: {created_tx.id})"

         redirect_url_path = str(request.app.url_path_for('ui_view_inventory_summary'))
         query_params = python_urlencode({"message": success_message})
         redirect_url = f"{redirect_url_path}?{query_params}" if query_params else redirect_url_path
         return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    except ValueError as e:
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         product = product_service.get_product(db, product_id=product_id)
         form_data_dict['category_id'] = product.category_id if product else None
         return templates.TemplateResponse("inventory/stock_in.html", {
             "request": request, "categories": categories, "locations": locations,
             "error": str(e), "form_data": form_data_dict
         }, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         product = product_service.get_product(db, product_id=product_id)
         form_data_dict['category_id'] = product.category_id if product else None
         print(f"Unexpected stock-in form error: {type(e).__name__} - {e}")
         return templates.TemplateResponse("inventory/stock_in.html", {
             "request": request, "categories": categories, "locations": locations,
             "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึกสต็อกเข้า", "form_data": form_data_dict
         }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@ui_router.get("/adjust/", response_class=HTMLResponse, name="ui_show_adjustment_form")
async def ui_show_adjustment_form(request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
    categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
    # Define standard adjustment reasons
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
    # Re-fetch reasons for error case
    adjustment_reasons = [ "สินค้าเสียหาย", "สินค้าหมดอายุ", "แก้ไขยอดจากการนับสต็อก - เพิ่ม", "แก้ไขยอดจากการนับสต็อก - ลด", "ใช้ภายใน", "ส่งคืนผู้ขาย", "อื่นๆ" ]

    if quantity_change == 0:
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         product = product_service.get_product(db, product_id=product_id)
         form_data_dict['category_id'] = product.category_id if product else None
         return templates.TemplateResponse("inventory/adjustment.html", {
             "request": request, "categories": categories, "locations": locations, "reasons": adjustment_reasons,
             "error": "จำนวนที่เปลี่ยนแปลงต้องไม่เป็นศูนย์", "form_data": form_data_dict
         }, status_code=status.HTTP_400_BAD_REQUEST)

    try:
        adjustment_data_schema = schemas.StockAdjustmentSchema(**form_data_dict)
        inventory_service.record_stock_adjustment(db=db, adjustment_data=adjustment_data_schema)
        # Get product name for message
        product = product_service.get_product(db, product_id=product_id)
        product_name = product.name if product else f"ID {product_id}"
        success_message = f"บันทึกการปรับปรุงสต็อก '{product_name}' (จำนวน: {quantity_change:+}) เรียบร้อยแล้ว"

        redirect_url_path = str(request.app.url_path_for('ui_view_inventory_summary'))
        query_params = python_urlencode({"message": success_message})
        redirect_url = f"{redirect_url_path}?{query_params}" if query_params else redirect_url_path
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         product = product_service.get_product(db, product_id=product_id)
         form_data_dict['category_id'] = product.category_id if product else None
         return templates.TemplateResponse("inventory/adjustment.html", {
             "request": request, "categories": categories, "locations": locations, "reasons": adjustment_reasons,
             "error": str(e), "form_data": form_data_dict
         }, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         product = product_service.get_product(db, product_id=product_id)
         form_data_dict['category_id'] = product.category_id if product else None
         print(f"Unexpected adjustment form error: {type(e).__name__} - {e}")
         return templates.TemplateResponse("inventory/adjustment.html", {
             "request": request, "categories": categories, "locations": locations, "reasons": adjustment_reasons,
             "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึกการปรับปรุงสต็อก", "form_data": form_data_dict
         }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@ui_router.get("/near-expiry/", response_class=HTMLResponse, name="ui_near_expiry_report")
async def ui_near_expiry_report(
    request: Request, db: Session = Depends(get_db),
    days_ahead: int = Query(30, ge=1),
    page: int = Query(1, ge=1),
    limit: int = Query(15, ge=1)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    skip = (page - 1) * limit
    report_data = inventory_service.get_near_expiry_transactions(db, days_ahead=days_ahead, skip=skip, limit=limit)
    total_count = report_data.get("total_count", 0)
    items = report_data.get("transactions", [])
    total_pages = math.ceil(total_count / limit) if limit > 0 else 0
    today_date = date.today()

    # --- Create Filter Link Helper for Pagination ---
    base_near_expiry_url_path = str(request.app.url_path_for('ui_near_expiry_report'))
    def _create_filter_link_for_template(**kwargs_to_update):
        current_request_params = dict(request.query_params)
        final_query_params = {}
        # Carry over 'limit' and 'days_ahead' unless changed
        for key in ['limit', 'days_ahead']:
             if key not in kwargs_to_update and key in current_request_params:
                 final_query_params[key] = current_request_params[key]
             elif key in kwargs_to_update and kwargs_to_update[key] is not None:
                 final_query_params[key] = str(kwargs_to_update[key])
        # Handle 'page'
        if 'page' in kwargs_to_update and kwargs_to_update['page'] is not None:
             final_query_params['page'] = str(kwargs_to_update['page'])
        elif 'page' in current_request_params:
             final_query_params['page'] = current_request_params['page']
        # else: defaults to 1 or absent
        query_string = python_urlencode(final_query_params)
        return f"{base_near_expiry_url_path}?{query_string}" if query_string else base_near_expiry_url_path
    # ----------------------------------------------

    return templates.TemplateResponse("reports/near_expiry.html", {
        "request": request, "transactions": items, "days_ahead": days_ahead,
        "page": page, "limit": limit, "total_count": total_count,
        "total_pages": total_pages, "today": today_date, "timedelta": timedelta,
        "skip": skip,
        "create_filter_link": _create_filter_link_for_template # Pass helper to template
    })

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
    form_data_dict = {
        "product_id": product_id, "from_location_id": from_location_id,
        "to_location_id": to_location_id, "quantity": quantity, "notes": notes
    }
    if from_location_id == to_location_id:
        error = "สถานที่จัดเก็บต้นทางและปลายทางต้องแตกต่างกัน"
        locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
        categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
        product = product_service.get_product(db, product_id=product_id)
        form_data_dict['category_id'] = product.category_id if product else None # Add category_id for pre-selection
        return templates.TemplateResponse("inventory/transfer.html", {
            "request": request, "locations": locations, "categories": categories,
            "form_data": form_data_dict, "error": error
        }, status_code=status.HTTP_400_BAD_REQUEST)
    try:
        transfer_data_schema = schemas.StockTransferSchema(**form_data_dict)
        tx_out, tx_in = inventory_service.record_stock_transfer(db=db, transfer_data=transfer_data_schema)
        # Get names for message
        product = product_service.get_product(db, product_id=product_id)
        product_name = product.name if product else f"ID {product_id}"
        from_loc = location_service.get_location(db, location_id=from_location_id)
        from_loc_name = from_loc.name if from_loc else f"ID {from_location_id}"
        to_loc = location_service.get_location(db, location_id=to_location_id)
        to_loc_name = to_loc.name if to_loc else f"ID {to_location_id}"
        success_message = f"โอนย้าย '{product_name}' จำนวน {quantity} จาก '{from_loc_name}' ไปยัง '{to_loc_name}' เรียบร้อยแล้ว (Tx: {tx_out.id} -> {tx_in.id})"

        redirect_url_path = str(request.app.url_path_for('ui_view_inventory_summary'))
        query_params = python_urlencode({"message": success_message})
        redirect_url = f"{redirect_url_path}?{query_params}" if query_params else redirect_url_path
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         product = product_service.get_product(db, product_id=product_id)
         form_data_dict['category_id'] = product.category_id if product else None # Add category_id for pre-selection
         return templates.TemplateResponse("inventory/transfer.html", {
             "request": request, "locations": locations, "categories": categories,
             "form_data": form_data_dict, "error": str(e)
         }, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         product = product_service.get_product(db, product_id=product_id)
         form_data_dict['category_id'] = product.category_id if product else None # Add category_id for pre-selection
         print(f"Unexpected transfer form error: {type(e).__name__} - {e}")
         return templates.TemplateResponse("inventory/transfer.html", {
             "request": request, "locations": locations, "categories": categories,
             "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึกการโอนย้าย", "form_data": form_data_dict
         }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --- NEW UI Route for Negative Stock Report ---
@ui_router.get("/negative-stock/", response_class=HTMLResponse, name="ui_negative_stock_report")
async def ui_negative_stock_report(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(15, ge=1),
    location: Optional[str] = Query(None), # Filter param for location ID
    category: Optional[str] = Query(None)  # Filter param for category ID
):
    templates = request.app.state.templates
    if templates is None:
        raise HTTPException(status_code=500, detail="Templates not configured")

    skip = (page - 1) * limit

    # Convert string query params to int, handle None or invalid values
    location_id: Optional[int] = None
    if location is not None and location.strip().isdigit():
        location_id = int(location)

    category_id: Optional[int] = None
    if category is not None and category.strip().isdigit():
        category_id = int(category)

    # Call the service function to get negative stock items
    report_data = inventory_service.get_negative_stock_items(
        db, location_id=location_id, category_id=category_id, skip=skip, limit=limit
    )
    items = report_data.get("items", [])
    total_count = report_data.get("total_count", 0)
    total_pages = math.ceil(total_count / limit) if limit > 0 else 0

    # Fetch data for filter dropdowns
    categories_data = category_service.get_categories(db=db, limit=1000)
    all_categories = categories_data.get("items", [])

    locations_data = location_service.get_locations(db=db, limit=1000)
    all_locations = locations_data.get("items", [])

    # --- Helper function to create filter links for this specific page ---
    base_report_url_path = str(request.app.url_path_for('ui_negative_stock_report'))
    def _create_filter_link_for_template(**kwargs_to_update):
        current_request_params = dict(request.query_params)
        final_query_params = {}

        # Carry over 'limit' unless explicitly changed
        if 'limit' not in kwargs_to_update and 'limit' in current_request_params:
            final_query_params['limit'] = current_request_params['limit']
        elif 'limit' in kwargs_to_update and kwargs_to_update['limit'] is not None:
            final_query_params['limit'] = str(kwargs_to_update['limit'])

        # Handle 'location' and 'category' filters (similar logic as inventory summary)
        for key in ['location', 'category']:
            if key in kwargs_to_update:
                value = kwargs_to_update[key]
                if value is not None and str(value).strip() != "":
                    final_query_params[key] = str(value)
            elif key in current_request_params and str(current_request_params[key]).strip() != "":
                final_query_params[key] = current_request_params[key]

        # Handle 'page' - reset if filters change
        if 'page' in kwargs_to_update:
            if kwargs_to_update['page'] is not None:
                final_query_params['page'] = str(kwargs_to_update['page'])
        elif any(k in kwargs_to_update for k in ['location', 'category']):
            final_query_params['page'] = '1' # Reset page if filters change
        elif 'page' in current_request_params:
            final_query_params['page'] = current_request_params['page']
        # else: defaults to 1 or absent

        query_string = python_urlencode(final_query_params)
        return f"{base_report_url_path}?{query_string}" if query_string else base_report_url_path
    # ---------------------------------------------------------------------

    context = {
        "request": request,
        "negative_stock_items": items, # Use a specific name for the items
        "page": page,
        "limit": limit,
        "total_count": total_count,
        "total_pages": total_pages,
        "skip": skip,
        "all_categories": all_categories,
        "selected_category_id": category_id, # Pass the selected ID
        "all_locations": all_locations,
        "selected_location_id": location_id, # Pass the selected ID
        "create_filter_link": _create_filter_link_for_template # Pass helper
    }
    # Render the new template file (we'll create this next)
    return templates.TemplateResponse("reports/negative_stock.html", context)
# ----------------------------------------------