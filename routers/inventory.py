# routers/inventory.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Tuple
from datetime import date, timedelta
from urllib.parse import urlencode
import math

# Absolute Imports
import schemas
import models # Import models เพื่อใช้ query ใหม่ใน API route (ถ้าจำเป็น)
from services import inventory_service, product_service, category_service, location_service
from database import get_db
# templates เข้าถึงผ่าน request.app.state.templates

API_INCLUDE_IN_SCHEMA = True

router = APIRouter(
    # prefix="/api/inventory", # Prefix กำหนดใน main.py
    tags=["API - สต็อกสินค้า"],
    include_in_schema=API_INCLUDE_IN_SCHEMA
)

ui_router = APIRouter(
    prefix="/ui/inventory", # Prefix สำหรับ UI Routes ของ Inventory
    tags=["หน้าเว็บ - สต็อกสินค้า"],
    include_in_schema=False
)

# --- API Routes ---

@router.get("/summary/", response_model=List[schemas.CurrentStock])
async def api_get_inventory_summary(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    stock_summary_data = inventory_service.get_current_stock_summary(db, skip=skip, limit=limit)
    return stock_summary_data["items"]

@router.post("/stock-in/", response_model=schemas.InventoryTransaction)
async def api_record_new_stock_in(stock_in: schemas.StockInSchema, db: Session = Depends(get_db)):
    try:
        created_transaction = inventory_service.record_stock_in(db=db, stock_in_data=stock_in)
        tx = db.query(models.InventoryTransaction).options(
             joinedload(models.InventoryTransaction.product).joinedload(models.Product.category),
             joinedload(models.InventoryTransaction.location)
         ).filter(models.InventoryTransaction.id == created_transaction.id).first()
        if tx is None: raise HTTPException(status_code=500, detail="ไม่สามารถดึงข้อมูล Transaction ที่สร้างได้")
        return tx
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบ" in error_message: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        else:
            print(f"Stock-in API Error: {error_message}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ไม่สามารถบันทึกสต็อกเข้า: {error_message}")
    except Exception as e:
        print(f"Unexpected API Error during stock-in: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดที่ไม่คาดคิด (API Stock-in)")

@router.post("/adjust/", response_model=schemas.InventoryTransaction, status_code=status.HTTP_201_CREATED)
async def api_record_stock_adjustment(adjustment: schemas.StockAdjustmentSchema, db: Session = Depends(get_db)):
    try:
        created_transaction = inventory_service.record_stock_adjustment(db=db, adjustment_data=adjustment)
        tx = db.query(models.InventoryTransaction).options(
             joinedload(models.InventoryTransaction.product).joinedload(models.Product.category),
             joinedload(models.InventoryTransaction.location)
         ).filter(models.InventoryTransaction.id == created_transaction.id).first()
        if tx is None: raise HTTPException(status_code=500, detail="ไม่สามารถดึงข้อมูล Transaction ที่สร้างได้")
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
        print(f"Unexpected API Error during adjustment: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดที่ไม่คาดคิด (API Adjustment)")

@router.get("/near-expiry/", response_model=List[schemas.InventoryTransaction])
async def api_get_near_expiry_report(
    days_ahead: int = 30, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    report_data = inventory_service.get_near_expiry_transactions(db, days_ahead=days_ahead, skip=skip, limit=limit)
    ids = [t.id for t in report_data["transactions"]]
    if not ids: return []
    transactions = db.query(models.InventoryTransaction).options(
        joinedload(models.InventoryTransaction.product).joinedload(models.Product.category),
        joinedload(models.InventoryTransaction.location)
    ).filter(models.InventoryTransaction.id.in_(ids)).order_by(models.InventoryTransaction.expiry_date.asc()).all()
    return transactions

@router.post("/transfer/", response_model=List[schemas.InventoryTransaction], status_code=status.HTTP_201_CREATED)
async def api_record_stock_transfer(
    transfer: schemas.StockTransferSchema, db: Session = Depends(get_db)
):
    try:
        tx_out, tx_in = inventory_service.record_stock_transfer(db=db, transfer_data=transfer)
        t_out = db.query(models.InventoryTransaction).options(
            joinedload(models.InventoryTransaction.product).joinedload(models.Product.category),
            joinedload(models.InventoryTransaction.location)
        ).filter(models.InventoryTransaction.id == tx_out.id).first()
        t_in = db.query(models.InventoryTransaction).options(
            joinedload(models.InventoryTransaction.product).joinedload(models.Product.category),
            joinedload(models.InventoryTransaction.location)
        ).filter(models.InventoryTransaction.id == tx_in.id).first()
        if not t_out or not t_in: raise HTTPException(status_code=500,detail="ไม่สามารถดึงข้อมูล Transaction ที่สร้างได้")
        return [t_out, t_in]
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบ" in error_message: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        elif "สต็อกไม่เพียงพอ" in error_message: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        elif "ต้องแตกต่างกัน" in error_message: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        else:
            print(f"Transfer API Error: {error_message}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ไม่สามารถโอนย้ายสต็อก: {error_message}")
    except Exception as e:
        print(f"Unexpected API Error during transfer: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดที่ไม่คาดคิด (API Transfer)")


# --- UI Routes ---

@ui_router.get("/summary/", response_class=HTMLResponse, name="ui_view_inventory_summary")
async def ui_view_inventory_summary(
    request: Request, page: int = 1, limit: int = 15, db: Session = Depends(get_db)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    skip = (page - 1) * limit
    if skip < 0: skip = 0
    message = request.query_params.get('message')
    error = request.query_params.get('error')
    report_data = inventory_service.get_current_stock_summary(db, skip=skip, limit=limit)
    items = report_data.get("items", [])
    total_count = report_data["total_count"]
    total_pages = math.ceil(total_count / limit) if limit > 0 else 0
    return templates.TemplateResponse("inventory/summary.html", {
        "request": request, "stock_summary": items, "page": page, "limit": limit,
        "total_count": total_count, "total_pages": total_pages,
        "message": message, "error": error, "skip": skip
    })

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
    expiry_date_str: Optional[str] = Form(None), notes: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = {"product_id": product_id, "location_id": location_id, "quantity": quantity, "cost_per_unit": cost_per_unit_str, "expiry_date": expiry_date_str, "notes": notes}
    cost_per_unit_float: Optional[float] = None
    if cost_per_unit_str is not None and cost_per_unit_str.strip() != "":
        try:
            cost_per_unit_float = float(cost_per_unit_str)
            if cost_per_unit_float < 0: raise ValueError("ต้นทุนต่อหน่วยต้องไม่ติดลบ")
        except ValueError:
             locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
             categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
             return templates.TemplateResponse("inventory/stock_in.html", {"request": request, "categories": categories, "locations": locations, "error": "รูปแบบต้นทุนต่อหน่วยไม่ถูกต้อง กรุณาใส่ตัวเลข", "form_data": form_data_dict }, status_code=status.HTTP_400_BAD_REQUEST)
    expiry_date_obj: Optional[date] = None
    if expiry_date_str:
        try: expiry_date_obj = date.fromisoformat(expiry_date_str)
        except ValueError:
             locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
             categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
             return templates.TemplateResponse("inventory/stock_in.html", { "request": request, "categories": categories, "locations": locations, "error": "รูปแบบวันที่หมดอายุไม่ถูกต้อง กรุณาใช้ YYYY-MM-DD", "form_data": form_data_dict }, status_code=status.HTTP_400_BAD_REQUEST)
    try:
         stock_in_data = schemas.StockInSchema(product_id=product_id, location_id=location_id, quantity=quantity, cost_per_unit=cost_per_unit_float, expiry_date=expiry_date_obj, notes=notes)
         inventory_service.record_stock_in(db=db, stock_in_data=stock_in_data)
         success_message = f"บันทึกการรับสินค้าเข้า (รหัสสินค้า: {product_id}, จำนวน: {quantity}) เรียบร้อยแล้ว"
         query_params = urlencode({"message": success_message})
         redirect_url = f"{request.app.url_path_for('ui_view_inventory_summary')}?{query_params}" # Redirect ไป Summary
         return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         return templates.TemplateResponse("inventory/stock_in.html", { "request": request, "categories": categories, "locations": locations, "error": str(e), "form_data": form_data_dict }, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         print(f"Unexpected stock-in form error: {e}")
         return templates.TemplateResponse("inventory/stock_in.html", { "request": request, "categories": categories, "locations": locations, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึกสต็อกเข้า", "form_data": form_data_dict }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
        adjustment_data = schemas.StockAdjustmentSchema(**form_data_dict)
        inventory_service.record_stock_adjustment(db=db, adjustment_data=adjustment_data)
        success_message = f"บันทึกการปรับปรุงสต็อก (สินค้า ID: {product_id}, สถานที่ ID: {location_id}, จำนวน: {quantity_change:+}) เรียบร้อยแล้ว"
        query_params = urlencode({"message": success_message})
        redirect_url = f"{request.app.url_path_for('ui_view_inventory_summary')}?{query_params}"
        return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         return templates.TemplateResponse("inventory/adjustment.html", { "request": request, "categories": categories, "locations": locations, "reasons": adjustment_reasons, "error": str(e), "form_data": form_data_dict }, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         print(f"Unexpected adjustment form error: {e}")
         return templates.TemplateResponse("inventory/adjustment.html", { "request": request, "categories": categories, "locations": locations, "reasons": adjustment_reasons, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึกการปรับปรุงสต็อก", "form_data": form_data_dict }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@ui_router.get("/near-expiry/", response_class=HTMLResponse, name="ui_near_expiry_report")
async def ui_near_expiry_report(
    request: Request, db: Session = Depends(get_db),
    days_ahead: int = 30, page: int = 1, limit: int = 15
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    skip = (page - 1) * limit
    if skip < 0: skip = 0
    if days_ahead < 1: days_ahead = 1
    report_data = inventory_service.get_near_expiry_transactions(db, days_ahead=days_ahead, skip=skip, limit=limit)
    total_count = report_data["total_count"]
    items = report_data["transactions"]
    total_pages = math.ceil(total_count / limit) if limit > 0 else 0
    today_date = date.today()
    return templates.TemplateResponse("reports/near_expiry.html", {
        "request": request, "transactions": items, "days_ahead": days_ahead,
        "page": page, "limit": limit, "total_count": total_count,
        "total_pages": total_pages, "today": today_date, "timedelta": timedelta, # timedelta ถูกส่งไป
        "skip": skip
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
    form_data_dict = {"product_id": product_id, "from_location_id": from_location_id, "to_location_id": to_location_id, "quantity": quantity, "notes": notes }
    if from_location_id == to_location_id:
        error = "สถานที่จัดเก็บต้นทางและปลายทางต้องแตกต่างกัน"
        locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
        categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
        return templates.TemplateResponse("inventory/transfer.html", { "request": request, "locations": locations, "categories": categories, "form_data": form_data_dict, "error": error }, status_code=status.HTTP_400_BAD_REQUEST)
    try:
        transfer_data = schemas.StockTransferSchema(**form_data_dict)
        tx_out, tx_in = inventory_service.record_stock_transfer(db=db, transfer_data=transfer_data)
        success_message = f"โอนย้ายสินค้า ID {product_id} จำนวน {quantity} จากสถานที่ ID {from_location_id} ไปยัง ID {to_location_id} เรียบร้อยแล้ว"
        query_params = urlencode({"message": success_message})
        redirect_url = f"{request.app.url_path_for('ui_view_inventory_summary')}?{query_params}"
        return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         return templates.TemplateResponse("inventory/transfer.html", { "request": request, "locations": locations, "categories": categories, "form_data": form_data_dict, "error": str(e) }, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         locations_data = location_service.get_locations(db=db, limit=1000); locations = locations_data.get("items", [])
         categories_data = category_service.get_categories(db=db, limit=1000); categories = categories_data.get("items", [])
         print(f"Unexpected transfer form error: {e}")
         return templates.TemplateResponse("inventory/transfer.html", { "request": request, "locations": locations, "categories": categories, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะบันทึกการโอนย้าย", "form_data": form_data_dict }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)