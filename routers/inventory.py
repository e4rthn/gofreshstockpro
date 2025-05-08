# routers/inventory.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload, defer #<-- เพิ่ม defer
from typing import List, Optional, Dict, Any, Tuple #<-- เพิ่ม Dict, Any, Tuple

# Adjust imports
import schemas
import models
from services import inventory_service # Service ที่เกี่ยวข้อง
from database import get_db
from models import CurrentStock # Import model โดยตรงสำหรับ Query

API_INCLUDE_IN_SCHEMA = True

# API Router (Prefix /api/inventory กำหนดใน main.py)
router = APIRouter(
    tags=["API - สต็อกสินค้า"],
    include_in_schema=API_INCLUDE_IN_SCHEMA
)

# --- API Routes Only ---
@router.get("/summary/", response_model=List[schemas.CurrentStock])
async def api_get_inventory_summary(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    category_id_str: Optional[str] = Query(None, alias="category_id"),
    location_id_str: Optional[str] = Query(None, alias="location_id"),
    db: Session = Depends(get_db)
):
    """ ดึงข้อมูลสรุปสต็อกคงคลัง (API) """
    category_id: Optional[int] = None
    if category_id_str is not None and category_id_str.strip():
        try: category_id = int(category_id_str)
        except ValueError: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category_id format for API.")

    location_id: Optional[int] = None
    if location_id_str is not None and location_id_str.strip():
        try: location_id = int(location_id_str)
        except ValueError: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid location_id format for API.")

    stock_summary_data = inventory_service.get_current_stock_summary(
        db, skip=skip, limit=limit, category_id=category_id, location_id=location_id
    )
    # API returns just the list of items
    return stock_summary_data.get("items", [])

@router.post("/stock-in/", response_model=schemas.InventoryTransaction)
async def api_record_new_stock_in(stock_in: schemas.StockInSchema, db: Session = Depends(get_db)):
    """ บันทึกการรับสินค้าเข้า (API) """
    try:
        # Service handles expiry calculation logic
        created_transaction = inventory_service.record_stock_in(db=db, stock_in_data=stock_in)
        # Query again with joins needed for the response model
        tx = db.query(models.InventoryTransaction).options(
             joinedload(models.InventoryTransaction.product).joinedload(models.Product.category),
             joinedload(models.InventoryTransaction.location)
         ).filter(models.InventoryTransaction.id == created_transaction.id).first()
        if tx is None:
            raise HTTPException(status_code=500, detail="Could not retrieve the created transaction with details.")
        return tx
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบ" in error_message: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        elif "กรุณาระบุ Production Date หรือ Expiry Date" in error_message: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        else: print(f"Stock-in API Error: {error_message}"); raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ไม่สามารถบันทึกสต็อกเข้า: {error_message}")
    except Exception as e: print(f"Unexpected API Error during stock-in: {type(e).__name__} - {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดที่ไม่คาดคิด (API Stock-in)")

@router.post("/adjust/", response_model=schemas.InventoryTransaction, status_code=status.HTTP_201_CREATED)
async def api_record_stock_adjustment(adjustment: schemas.StockAdjustmentSchema, db: Session = Depends(get_db)):
    """ บันทึกการปรับปรุงสต็อก (API) """
    try:
        created_transaction = inventory_service.record_stock_adjustment(db=db, adjustment_data=adjustment)
        # Query again with joins needed for the response model
        tx = db.query(models.InventoryTransaction).options(
             joinedload(models.InventoryTransaction.product).joinedload(models.Product.category),
             joinedload(models.InventoryTransaction.location)
         ).filter(models.InventoryTransaction.id == created_transaction.id).first()
        if tx is None: raise HTTPException(status_code=500, detail="Could not retrieve the created adjustment transaction with details.")
        return tx
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบ" in error_message: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        elif "สต็อกไม่เพียงพอ" in error_message: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        elif "ต้องไม่เป็นศูนย์" in error_message: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        else: print(f"Adjustment API Error: {error_message}"); raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ไม่สามารถบันทึกการปรับปรุงสต็อก: {error_message}")
    except Exception as e: print(f"Unexpected API Error during adjustment: {type(e).__name__} - {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดที่ไม่คาดคิด (API Adjustment)")

@router.get("/near-expiry/", response_model=List[schemas.InventoryTransaction])
async def api_get_near_expiry_report(
    days_ahead: int = Query(30, ge=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    db: Session = Depends(get_db)
):
    """ ดึงรายงานสินค้าใกล้หมดอายุ (API) """
    report_data = inventory_service.get_near_expiry_transactions(db, days_ahead=days_ahead, skip=skip, limit=limit)
    # API returns just the list of transactions
    return report_data.get("transactions", [])

@router.post("/transfer/", response_model=List[schemas.InventoryTransaction], status_code=status.HTTP_201_CREATED)
async def api_record_stock_transfer(
    transfer: schemas.StockTransferSchema, db: Session = Depends(get_db)
):
    """ บันทึกการโอนย้ายสต็อก (API) """
    try:
        tx_out, tx_in = inventory_service.record_stock_transfer(db=db, transfer_data=transfer)
        # Query again with joins needed for the response model
        t_out = db.query(models.InventoryTransaction).options(joinedload(models.InventoryTransaction.product).joinedload(models.Product.category),joinedload(models.InventoryTransaction.location)).filter(models.InventoryTransaction.id == tx_out.id).first()
        t_in = db.query(models.InventoryTransaction).options(joinedload(models.InventoryTransaction.product).joinedload(models.Product.category),joinedload(models.InventoryTransaction.location)).filter(models.InventoryTransaction.id == tx_in.id).first()
        if not t_out or not t_in: raise HTTPException(status_code=500, detail="ไม่สามารถดึงข้อมูล Transaction โอนย้ายที่สร้างได้")
        return [t_out, t_in] # Return list containing both transactions
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบ" in error_message: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        elif "สต็อกไม่เพียงพอ" in error_message: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        elif "ต้องแตกต่างกัน" in error_message: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        else: print(f"Transfer API Error: {error_message}"); raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ไม่สามารถโอนย้ายสต็อก: {error_message}")
    except Exception as e: print(f"Unexpected API Error during transfer: {type(e).__name__} - {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดที่ไม่คาดคิด (API Transfer)")


# --- API Endpoint สำหรับดึง Stock Level ของสินค้า ณ สถานที่เดียว ---
@router.get("/stock-level/{product_id}/{location_id}",
            response_model=schemas.CurrentStock, # หรือ Schema ที่ง่ายกว่า ถ้าต้องการแค่ quantity
            summary="Get Current Stock for a Specific Item and Location")
async def api_get_specific_stock_level(
    product_id: int,
    location_id: int,
    db: Session = Depends(get_db)
):
    """ ดึงข้อมูลสต็อกปัจจุบันสำหรับสินค้าและสถานที่เก็บที่ระบุ """
    # Query โดยตรงเพื่อดึงข้อมูลที่จำเป็นสำหรับ Response Model
    stock_record = db.query(models.CurrentStock).options(
         joinedload(models.CurrentStock.product).load_only(models.Product.id, models.Product.name, models.Product.sku), # Load เฉพาะ field ที่จำเป็น
         joinedload(models.CurrentStock.location).load_only(models.Location.id, models.Location.name)
     ).filter(
        models.CurrentStock.product_id == product_id,
        models.CurrentStock.location_id == location_id
    ).first()

    if stock_record is None:
        # คืน 404 ถ้าไม่มี record สต็อกนี้เลย
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                             detail=f"ไม่พบข้อมูลสต็อกสำหรับ Product ID {product_id} ที่ Location ID {location_id}")

    return stock_record
# --- สิ้นสุด API Endpoint ---

# --- ไม่มี UI Routes ในไฟล์นี้แล้ว ---