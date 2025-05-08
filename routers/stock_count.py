# routers/stock_count.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List

# Adjust imports
import schemas
import models
from services import stock_count_service
from database import get_db

API_INCLUDE_IN_SCHEMA = True

# API Router (Prefix defined in main.py)
router = APIRouter(
    tags=["API - ตรวจนับสต็อก"],
    include_in_schema=API_INCLUDE_IN_SCHEMA
)

# --- API Routes Only ---

# Session API Routes
@router.post("/sessions/", response_model=schemas.StockCountSession, status_code=status.HTTP_201_CREATED)
async def api_create_new_stock_count_session(
    session_in: schemas.StockCountSessionCreate, db: Session = Depends(get_db)
):
    """ สร้างรอบนับสต็อกใหม่ (API) """
    try:
        new_session = stock_count_service.create_stock_count_session(db=db, session_data=session_in)
        # Query again to load location for response model (service returns basic model)
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
    return sessions_data.get("items", []) # Return list

@router.get("/sessions/{session_id}", response_model=schemas.StockCountSession)
async def api_get_one_stock_count_session(session_id: int, db: Session = Depends(get_db)):
    """ ดึงข้อมูลรอบนับสต็อกตาม ID (API) """
    # Service function already loads relations needed for the schema
    session = stock_count_service.get_stock_count_session(db, session_id=session_id)
    if session is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    return session

# Item API Routes
@router.post("/sessions/{session_id}/items", response_model=schemas.StockCountItem, status_code=status.HTTP_201_CREATED)
async def api_add_item_to_session(
    session_id: int, item_in: schemas.StockCountItemCreate, db: Session = Depends(get_db)
):
    """ เพิ่มสินค้าเข้ารอบนับสต็อก (API) """
    try:
        created_item = stock_count_service.add_product_to_session(db=db, session_id=session_id, item_data=item_in)
        # Query again to load product basic info for response model
        item_with_details = db.query(models.StockCountItem).options(
            joinedload(models.StockCountItem.product)
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
        # Service function name might differ, adjust if needed
        updated_item = stock_count_service.update_counted_quantity(db=db, item_id=item_id, item_update_data=item_update)
        # Query again to load product for response model
        item_with_details = db.query(models.StockCountItem).options(
            joinedload(models.StockCountItem.product)
        ).filter(models.StockCountItem.id == updated_item.id).first()
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
        # Fetch full session details again for the response
        session_with_details = stock_count_service.get_stock_count_session(db, session_id=closed_session.id)
        if not session_with_details: raise HTTPException(status_code=500, detail="Could not fetch closed session details")
        return session_with_details
    except ValueError as e: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(f"Error closing session (API) {session_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดในการปิดรอบนับสต็อก")


# --- No UI Routes Here Anymore ---