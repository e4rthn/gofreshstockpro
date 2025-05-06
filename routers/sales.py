# routers/sales.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload, subqueryload
from typing import List, Optional, Dict, Any
from datetime import date, datetime, time, timedelta
import math
from urllib.parse import urlencode

# Absolute Imports
import schemas
import models
from services import sales_service, location_service, category_service, product_service
from database import get_db

API_INCLUDE_IN_SCHEMA = True

router = APIRouter(
    tags=["API - การขาย (Sales)"],
    include_in_schema=API_INCLUDE_IN_SCHEMA
)

@router.post("/",
             response_model=schemas.Sale, # Should be schemas.Sale
             status_code=status.HTTP_201_CREATED)
async def api_record_new_sale(
    sale: schemas.SaleCreate, db: Session = Depends(get_db)
):
    """ บันทึกข้อมูลการขายใหม่ (API) - สามารถระบุ allow_negative_stock_on_sale ใน request body ถ้าต้องการ """
    # For API, allow_negative_stock_on_sale might be part of SaleCreate schema or a query param
    # For this example, assuming SaleCreate might get an optional field for it.
    # Or, for simplicity, API calls always enforce stock unless business rule changes.
    allow_negative_via_api = getattr(sale, 'allow_negative_stock_on_sale', False) # Example if added to schema

    try:
        created_sale = sales_service.record_sale(
            db=db,
            sale_data=sale,
            allow_negative_stock_on_sale=allow_negative_via_api # Pass the flag
        )
        return created_sale
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบ" in error_message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        # Check for specific stock error message from the service
        elif "สต็อกในระบบไม่เพียงพอ" in error_message or "สต็อกไม่เพียงพอ" in error_message :
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        elif "ไม่มีรายการสินค้า" in error_message:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        else:
            print(f"Sale recording ValueError (API): {error_message}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ไม่สามารถบันทึกการขาย: {error_message}")
    except Exception as e:
        print(f"Unexpected Error during sale recording (API): {type(e).__name__} - {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดภายในระบบขณะบันทึกการขาย (API)")


@router.get("/report/", response_model=List[schemas.Sale]) # Should be List[schemas.Sale]
async def api_get_sales_report(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, gt=0),
    db: Session = Depends(get_db)
):
    report_data = sales_service.get_sales_report(
        db, start_date=start_date, end_date=end_date, skip=skip, limit=limit
    )
    return report_data["sales"]


ui_router = APIRouter(
    tags=["หน้าเว็บ - การขายและรายงาน"],
    include_in_schema=False
)

@ui_router.get("/pos/", response_class=HTMLResponse, name="ui_show_pos_form")
async def ui_show_pos_form(request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if not templates: raise HTTPException(status_code=500, detail="Templates not configured")

    locations_data = location_service.get_locations(db=db, limit=1000)
    categories_data = category_service.get_categories(db=db, limit=1000)

    message = request.query_params.get('message')
    error = request.query_params.get('error')
    ask_override = request.query_params.get('ask_override') # Get the flag

    return templates.TemplateResponse("pos/form.html", {
        "request": request,
        "locations": locations_data.get("items", []),
        "categories": categories_data.get("items", []),
        "message": message,
        "error": error,
        "ask_override": ask_override == "true" # Pass as boolean to template
    })

@ui_router.post("/pos/", response_class=HTMLResponse, name="ui_handle_pos_form")
async def ui_handle_pos_form(
    request: Request,
    db: Session = Depends(get_db),
    location_id: int = Form(...),
    notes: Optional[str] = Form(None),
    item_product_id: List[int] = Form(None, alias="item_product_id"),
    item_quantity: List[int] = Form(None, alias="item_quantity"),
    item_unit_price: List[float] = Form(None, alias="item_unit_price"),
    override_stock_check: Optional[bool] = Form(False) # Field from the checkbox
):
    templates = request.app.state.templates
    if not templates: raise HTTPException(status_code=500, detail="Templates not configured")

    base_pos_url = str(request.app.url_path_for('ui_show_pos_form'))

    if not item_product_id or \
       not (item_quantity and len(item_product_id) == len(item_quantity)) or \
       not (item_unit_price and len(item_product_id) == len(item_unit_price)):
        error_message = "กรุณาเพิ่มรายการสินค้าอย่างน้อย 1 รายการ หรือข้อมูลรายการสินค้าไม่สมบูรณ์"
        query_params = urlencode({"error": error_message})
        return RedirectResponse(url=f"{base_pos_url}?{query_params}", status_code=status.HTTP_303_SEE_OTHER)

    sale_items_create: List[schemas.SaleItemCreate] = []
    for i in range(len(item_product_id)):
        if item_quantity[i] <= 0 or item_unit_price[i] < 0:
             error_message = f"จำนวนหรือราคาของสินค้า (ID: {item_product_id[i]}) ไม่ถูกต้อง"
             query_params = urlencode({"error": error_message})
             return RedirectResponse(url=f"{base_pos_url}?{query_params}", status_code=status.HTTP_303_SEE_OTHER)
        sale_items_create.append(schemas.SaleItemCreate(
            product_id=item_product_id[i],
            quantity=item_quantity[i],
            unit_price=item_unit_price[i]
        ))

    sale_data = schemas.SaleCreate(location_id=location_id, notes=notes, items=sale_items_create)

    try:
        created_sale = sales_service.record_sale(
            db=db,
            sale_data=sale_data,
            allow_negative_stock_on_sale=override_stock_check # Pass the override flag
        )
        success_message = (f"บันทึกการขายรหัส #{created_sale.id} จำนวน {len(created_sale.items)} "
                           f"รายการ ยอดรวม {created_sale.total_amount:.2f} บาท เรียบร้อยแล้ว")
        
        inventory_summary_url = str(request.app.url_path_for('ui_view_inventory_summary'))
        query_params = urlencode({"message": success_message})
        return RedirectResponse(url=f"{inventory_summary_url}?{query_params}", status_code=status.HTTP_303_SEE_OTHER)

    except ValueError as e:
        error_message = str(e)
        params_for_redirect = {"error": error_message}
        if "สต็อกในระบบไม่เพียงพอ" in error_message and not override_stock_check:
            params_for_redirect["ask_override"] = "true"
        
        query_params = urlencode(params_for_redirect)
        return RedirectResponse(url=f"{base_pos_url}?{query_params}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
         print(f"Unexpected POS form error: {type(e).__name__} - {e}")
         error_message = "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึกการขาย (โปรดตรวจสอบ log)"
         query_params = urlencode({"error": error_message})
         return RedirectResponse(url=f"{base_pos_url}?{query_params}", status_code=status.HTTP_303_SEE_OTHER)

@ui_router.get("/sales/report/", response_class=HTMLResponse, name="ui_sales_report")
async def ui_sales_report(
    request: Request, db: Session = Depends(get_db),
    start_date_str: Optional[str] = Query(None, alias="start_date"),
    end_date_str: Optional[str] = Query(None, alias="end_date"),
    page: int = Query(1, gt=0), limit: int = Query(15, gt=0)
):
    templates = request.app.state.templates
    if not templates: raise HTTPException(status_code=500, detail="Templates not configured")

    start_date_obj: Optional[date] = None
    end_date_obj: Optional[date] = None
    parse_error: Optional[str] = None

    if start_date_str and start_date_str.strip():
        try: start_date_obj = date.fromisoformat(start_date_str)
        except ValueError: parse_error = f"รูปแบบวันที่เริ่มต้นไม่ถูกต้อง: '{start_date_str}' (ต้องเป็น YYYY-MM-DD)"
    if end_date_str and end_date_str.strip():
        try: end_date_obj = date.fromisoformat(end_date_str)
        except ValueError:
            error_detail = f"รูปแบบวันที่สิ้นสุดไม่ถูกต้อง: '{end_date_str}' (ต้องเป็น YYYY-MM-DD)"
            parse_error = f"{parse_error}; {error_detail}" if parse_error else error_detail

    current_skip = (page - 1) * limit if page > 0 else 0
    context_vars = {
        "request": request, "start_date": start_date_str or "", "end_date": end_date_str or "",
        "page": page, "limit": limit, "skip": current_skip,
        "sales_data_with_profit": [], "grand_total_profit": 0.0,
        "total_count": 0, "total_pages": 0, "error": parse_error
    }

    if parse_error:
        return templates.TemplateResponse("reports/sales.html", context_vars, status_code=status.HTTP_400_BAD_REQUEST)

    report_data_dict = sales_service.get_sales_report(db, start_date=start_date_obj, end_date=end_date_obj, skip=current_skip, limit=limit)
    sales_list = report_data_dict.get("sales", [])
    total_count = report_data_dict.get("total_count", 0)
    total_pages = math.ceil(total_count / limit) if limit > 0 else 0

    sales_data_with_profit = []
    grand_total_profit_page = 0.0
    for sale_obj in sales_list:
        estimated_profit_for_sale = 0.0
        if sale_obj.items:
            for item in sale_obj.items:
                if item.product and item.product.standard_cost is not None and item.unit_price is not None: # Ensure price is not None
                    cost_of_goods_sold = item.quantity * item.product.standard_cost
                    revenue_from_item = item.quantity * item.unit_price
                    estimated_profit_for_sale += (revenue_from_item - cost_of_goods_sold)
        sales_data_with_profit.append({"sale_obj": sale_obj, "estimated_profit": estimated_profit_for_sale})
        grand_total_profit_page += estimated_profit_for_sale
    
    context_vars.update({
        "sales_data_with_profit": sales_data_with_profit,
        "grand_total_profit": grand_total_profit_page,
        "total_count": total_count, "total_pages": total_pages,
        "error": None # Clear any previous parse error if we've successfully fetched data
    })
    return templates.TemplateResponse("reports/sales.html", context_vars)