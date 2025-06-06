# routers/inventory.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

import schemas
import models
from services import inventory_service # Assuming this service is correctly implemented
from database import get_db
# from models import CurrentStock # Only if directly used, otherwise schemas are enough

API_INCLUDE_IN_SCHEMA = True

# This 'router' instance is what main.py expects from 'api_inventory_router_module.router'
router = APIRouter(
    tags=["API - สต็อกสินค้า"],
    include_in_schema=API_INCLUDE_IN_SCHEMA
    # The prefix "/api/inventory" is applied in main.py when this router is included
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
    return stock_summary_data.get("items", [])

@router.post("/stock-in/", response_model=schemas.InventoryTransaction)
async def api_record_new_stock_in(stock_in: schemas.StockInSchema, db: Session = Depends(get_db)):
    try:
        created_transaction = inventory_service.record_stock_in(db=db, stock_in_data=stock_in)
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
        if tx is None: raise HTTPException(status_code=500, detail="Could not retrieve the created adjustment transaction with details.")
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
    report_data = inventory_service.get_near_expiry_transactions(db, days_ahead=days_ahead, skip=skip, limit=limit)
    return report_data.get("transactions", [])

@router.post("/transfer/", response_model=List[schemas.InventoryTransaction], status_code=status.HTTP_201_CREATED)
async def api_record_stock_transfer(
    transfer: schemas.StockTransferSchema, db: Session = Depends(get_db)
):
    try:
        tx_out, tx_in = inventory_service.record_stock_transfer(db=db, transfer_data=transfer)
        # Re-query for response model including relationships
        t_out_full = db.query(models.InventoryTransaction).options(joinedload(models.InventoryTransaction.product).joinedload(models.Product.category),joinedload(models.InventoryTransaction.location)).filter(models.InventoryTransaction.id == tx_out.id).first()
        t_in_full = db.query(models.InventoryTransaction).options(joinedload(models.InventoryTransaction.product).joinedload(models.Product.category),joinedload(models.InventoryTransaction.location)).filter(models.InventoryTransaction.id == tx_in.id).first()
        if not t_out_full or not t_in_full: raise HTTPException(status_code=500, detail="ไม่สามารถดึงข้อมูล Transaction โอนย้ายที่สร้างได้")
        return [t_out_full, t_in_full]
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


@router.get("/stock-level/{product_id}/{location_id}",
            response_model=schemas.CurrentStock,
            summary="Get Current Stock for a Specific Item and Location")
async def api_get_specific_stock_level(
    product_id: int,
    location_id: int,
    db: Session = Depends(get_db)
):
    stock_record = db.query(models.CurrentStock).options(
         joinedload(models.CurrentStock.product).load_only(models.Product.id, models.Product.name, models.Product.sku),
         joinedload(models.CurrentStock.location).load_only(models.Location.id, models.Location.name)
     ).filter(
        models.CurrentStock.product_id == product_id,
        models.CurrentStock.location_id == location_id
    ).first()

    if stock_record is None:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                             detail=f"ไม่พบข้อมูลสต็อกสำหรับ Product ID {product_id} ที่ Location ID {location_id}")
    return stock_record