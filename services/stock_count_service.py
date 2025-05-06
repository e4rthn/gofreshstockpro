# services/stock_count_service.py
from sqlalchemy.orm import Session, joinedload, subqueryload
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

# Absolute Imports
import models
import schemas
from services import location_service, product_service, inventory_service # inventory_service ถูกเรียกใช้ที่นี่

def create_stock_count_session(db: Session, session_data: schemas.StockCountSessionCreate) -> models.StockCountSession:
    """ สร้างรอบนับสต็อกใหม่ """
    location = location_service.get_location(db, location_id=session_data.location_id)
    if not location: raise ValueError(f"ไม่พบสถานที่จัดเก็บ รหัส {session_data.location_id}")
    db_session = models.StockCountSession(
        location_id=session_data.location_id,
        notes=session_data.notes,
        status=models.StockCountStatus.OPEN
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session

def get_stock_count_session(db: Session, session_id: int) -> Optional[models.StockCountSession]:
    """ ดึงข้อมูลรอบนับสต็อกตาม ID พร้อมรายการสินค้าและ product """
    return db.query(models.StockCountSession).options(
        joinedload(models.StockCountSession.location),
        subqueryload(models.StockCountSession.items).joinedload(models.StockCountItem.product).joinedload(models.Product.category) # โหลด Category ด้วย
    ).filter(models.StockCountSession.id == session_id).first()

def get_stock_count_sessions(db: Session, skip: int = 0, limit: int = 100) -> Dict[str, Any]:
    """ ดึงรายการรอบนับสต็อกทั้งหมด พร้อม Location """
    query = db.query(models.StockCountSession).options(joinedload(models.StockCountSession.location))
    total_count = query.count()
    sessions = query.order_by(models.StockCountSession.start_date.desc()).offset(skip).limit(limit).all()
    return {"items": sessions, "total_count": total_count}

def add_product_to_session(db: Session, session_id: int, item_data: schemas.StockCountItemCreate) -> models.StockCountItem:
    """ เพิ่มสินค้าเข้ารอบนับ พร้อมดึงยอดคงเหลือปัจจุบันมาบันทึก """
    session = get_stock_count_session(db, session_id)
    if not session: raise ValueError(f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    if session.status not in [models.StockCountStatus.OPEN, models.StockCountStatus.COUNTING]:
        raise ValueError(f"ไม่สามารถเพิ่มสินค้าในรอบนับที่สถานะ {session.status.value} ได้")
    product = product_service.get_product(db, product_id=item_data.product_id)
    if not product: raise ValueError(f"ไม่พบสินค้า รหัส {item_data.product_id}")
    existing_item = db.query(models.StockCountItem).filter(
        models.StockCountItem.session_id == session_id,
        models.StockCountItem.product_id == item_data.product_id
    ).first()
    if existing_item: raise ValueError(f"สินค้า '{product.name}' มีอยู่ในรอบนับนี้แล้ว")
    current_stock = inventory_service.get_current_stock_record(db, product_id=item_data.product_id, location_id=session.location_id)
    system_qty = current_stock.quantity if current_stock else 0
    db_item = models.StockCountItem(
        session_id=session_id, product_id=item_data.product_id,
        system_quantity=system_qty, counted_quantity=None
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

def update_counted_quantity(db: Session, item_id: int, item_update_data: schemas.StockCountItemUpdate) -> models.StockCountItem:
    """ อัปเดตยอดนับจริงของรายการในรอบนับ (แก้ไข Query) """
    db_item = db.query(models.StockCountItem).options(
        joinedload(models.StockCountItem.session) # Join เพื่อเช็ค status
    ).filter(models.StockCountItem.id == item_id).first() # ไม่มี .with_for_update()
    if not db_item: raise ValueError(f"ไม่พบรายการตรวจนับ รหัส {item_id}")
    needs_session_commit = False
    if db_item.session.status == models.StockCountStatus.OPEN:
         db_item.session.status = models.StockCountStatus.COUNTING
         db.add(db_item.session); needs_session_commit = True
    elif db_item.session.status != models.StockCountStatus.COUNTING:
        raise ValueError(f"ไม่สามารถบันทึกยอดนับในรอบนับที่สถานะ {db_item.session.status.value} ได้ (ต้องเป็น COUNTING)")
    db_item.counted_quantity = item_update_data.counted_quantity
    db_item.count_date = datetime.utcnow()
    db.commit()
    db.refresh(db_item)
    if needs_session_commit:
        try: db.refresh(db_item.session)
        except Exception as refresh_err: print(f"Warning: could not refresh session: {refresh_err}")
    return db_item

def start_counting_session(db: Session, session_id: int) -> models.StockCountSession:
    """ เปลี่ยนสถานะรอบนับเป็น COUNTING """
    session = db.query(models.StockCountSession).filter(models.StockCountSession.id == session_id).with_for_update().first()
    if not session: raise ValueError(f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    if session.status != models.StockCountStatus.OPEN:
        raise ValueError(f"รอบนับนี้ไม่ได้อยู่ในสถานะ OPEN (สถานะปัจจุบัน: {session.status.value})")
    session.status = models.StockCountStatus.COUNTING
    db.commit()
    db.refresh(session)
    return session

def close_stock_count_session(db: Session, session_id: int) -> models.StockCountSession:
    """ ปิดรอบนับสต็อก และสร้าง Stock Adjustment สำหรับส่วนต่าง """
    session = db.query(models.StockCountSession).filter(models.StockCountSession.id == session_id).with_for_update().first()
    if not session: raise ValueError(f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    if session.status != models.StockCountStatus.COUNTING:
        raise ValueError(f"ไม่สามารถปิดรอบนับที่สถานะ {session.status.value} ได้ (ต้องเป็น COUNTING)")
    items_in_session = db.query(models.StockCountItem).filter(models.StockCountItem.session_id == session_id).all()
    uncounted_items = [item for item in items_in_session if item.counted_quantity is None]
    if uncounted_items:
        product_ids = [item.product_id for item in uncounted_items]
        raise ValueError(f"กรุณาบันทึกยอดนับให้ครบทุกรายการก่อนปิดรอบนับ (สินค้า ID ที่ยังไม่ได้นับ: {product_ids})")
    try:
        adjustments_created_count = 0
        for item in items_in_session:
            difference = item.difference
            if difference is not None and difference != 0:
                adjustment_data = schemas.StockAdjustmentSchema(
                    product_id=item.product_id, location_id=session.location_id,
                    quantity_change=difference, reason=f"ตรวจนับสต็อกรอบ #{session_id}",
                    notes=f"ยอดในระบบ: {item.system_quantity}, ยอดนับจริง: {item.counted_quantity}"
                )
                # เรียกใช้ inventory_service.record_stock_adjustment
                # แต่เนื่องจากอยู่ในไฟล์เดียวกัน สามารถเรียก record_stock_adjustment ได้โดยตรง
                inventory_service.record_stock_adjustment(db=db, adjustment_data=adjustment_data, allow_negative_stock_for_count=True) # Pass flag
                adjustments_created_count += 1
        session.status = models.StockCountStatus.CLOSED
        session.end_date = datetime.utcnow()
        db.commit()
    except Exception as e:
        db.rollback(); print(f"Error: {e}");
        if isinstance(e, ValueError): raise e
        else: raise ValueError(f"DB error closing session") from e
    db.refresh(session)
    print(f"Stock Count Session {session_id} closed. {adjustments_created_count} adjustments created.")
    return session

def cancel_stock_count_session(db: Session, session_id: int) -> models.StockCountSession:
    """ ยกเลิกรอบนับสต็อก (เปลี่ยนสถานะเป็น CANCELED) """
    session = db.query(models.StockCountSession).filter(models.StockCountSession.id == session_id).with_for_update().first()
    if not session: raise ValueError(f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    if session.status not in [models.StockCountStatus.OPEN, models.StockCountStatus.COUNTING]:
        raise ValueError(f"ไม่สามารถยกเลิกรอบนับที่สถานะ '{session.status.value}' ได้ (ต้องเป็น OPEN หรือ COUNTING)")
    session.status = models.StockCountStatus.CANCELED
    session.end_date = datetime.utcnow()
    try:
        db.commit()
    except Exception as e:
        db.rollback(); print(f"Error canceling session: {e}"); raise ValueError(f"DB error canceling session") from e
    db.refresh(session)
    print(f"Stock Count Session {session_id} canceled.")
    return session