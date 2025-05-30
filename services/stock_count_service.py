# services/stock_count_service.py
from sqlalchemy.orm import Session, joinedload, subqueryload
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

import models
import schemas
# inventory_service ถูกเรียกใช้ที่นี่สำหรับ record_stock_adjustment ตอน close session
from services import location_service, product_service, inventory_service

def create_stock_count_session(db: Session, session_data: schemas.StockCountSessionCreate) -> models.StockCountSession:
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
    return db.query(models.StockCountSession).options(
        joinedload(models.StockCountSession.location),
        subqueryload(models.StockCountSession.items).joinedload(models.StockCountItem.product).joinedload(models.Product.category)
    ).filter(models.StockCountSession.id == session_id).first()

def get_stock_count_sessions(db: Session, skip: int = 0, limit: int = 100) -> Dict[str, Any]:
    query = db.query(models.StockCountSession).options(joinedload(models.StockCountSession.location))
    total_count = query.count()
    sessions = query.order_by(models.StockCountSession.start_date.desc()).offset(skip).limit(limit).all()
    return {"items": sessions, "total_count": total_count}

def add_product_to_session(db: Session, session_id: int, item_data: schemas.StockCountItemCreate) -> models.StockCountItem:
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

    # ดึง current_stock จาก inventory_service
    current_stock_record = inventory_service.get_current_stock_record(db, product_id=item_data.product_id, location_id=session.location_id)
    system_qty = current_stock_record.quantity if current_stock_record else 0.0 # ให้เป็น float

    db_item = models.StockCountItem(
        session_id=session_id, product_id=item_data.product_id,
        system_quantity=system_qty, counted_quantity=None # counted_quantity เป็น float อยู่แล้ว
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

def update_counted_quantity(db: Session, item_id: int, item_update_data: schemas.StockCountItemUpdate) -> models.StockCountItem:
    # ใช้ with_for_update() หากต้องการ lock item ขณะอัปเดต
    db_item = db.query(models.StockCountItem).options(
        joinedload(models.StockCountItem.session, innerjoin=True) 
    ).filter(models.StockCountItem.id == item_id).with_for_update().first()

    if not db_item: raise ValueError(f"ไม่พบรายการตรวจนับ รหัส {item_id}")

    if db_item.session.status == models.StockCountStatus.OPEN:
        db_item.session.status = models.StockCountStatus.COUNTING
        # db.add(db_item.session) # SQLAlchemy มักจะ track การเปลี่ยนแปลงนี้ผ่าน relationship
    elif db_item.session.status != models.StockCountStatus.COUNTING:
        raise ValueError(f"ไม่สามารถบันทึกยอดนับในรอบนับที่สถานะ {db_item.session.status.value} ได้ (ต้องเป็น COUNTING)")

    db_item.counted_quantity = item_update_data.counted_quantity # เป็น float จาก schema
    db_item.count_date = datetime.utcnow()
    try:
        db.commit()
        db.refresh(db_item)
        if db_item.session: db.refresh(db_item.session)
    except Exception as e:
        db.rollback()
        print(f"DB error updating count for item {item_id}: {str(e)}")
        # ให้รายละเอียดของ error เดิมออกไป เพื่อให้ debug ได้ง่ายขึ้นใน UI
        raise ValueError(f"DB error updating count for item {item_id}: {type(e).__name__} - {e}") from e
    return db_item

def start_counting_session(db: Session, session_id: int) -> models.StockCountSession:
    session = db.query(models.StockCountSession).filter(models.StockCountSession.id == session_id).with_for_update().first()
    if not session: raise ValueError(f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    if session.status != models.StockCountStatus.OPEN:
        raise ValueError(f"รอบนับนี้ไม่ได้อยู่ในสถานะ OPEN (สถานะปัจจุบัน: {session.status.value})")
    session.status = models.StockCountStatus.COUNTING
    try:
        db.commit()
        db.refresh(session)
    except Exception as e:
        db.rollback()
        print(f"DB error starting count session {session_id}: {str(e)}")
        raise ValueError(f"DB error starting count session {session_id}") from e
    return session

def close_stock_count_session(db: Session, session_id: int) -> models.StockCountSession:
    session = db.query(models.StockCountSession).options(
        subqueryload(models.StockCountSession.items)
    ).filter(models.StockCountSession.id == session_id).with_for_update().first()

    if not session: raise ValueError(f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    if session.status != models.StockCountStatus.COUNTING:
        raise ValueError(f"ไม่สามารถปิดรอบนับที่สถานะ '{session.status.value}' ได้ (ต้องเป็น COUNTING)")

    items_in_session = session.items
    uncounted_items = [item for item in items_in_session if item.counted_quantity is None]
    if uncounted_items:
        product_ids_str = ", ".join(str(item.product_id) for item in uncounted_items)
        raise ValueError(f"กรุณาบันทึกยอดนับให้ครบทุกรายการก่อนปิดรอบนับ (สินค้า ID ที่ยังไม่ได้นับ: {product_ids_str})")

    try:
        adjustments_created_count = 0
        for item in items_in_session:
            difference = item.difference
            if difference is not None and difference != 0: # difference เป็น float
                adjustment_data_schema = schemas.StockAdjustmentSchema(
                    product_id=item.product_id, location_id=session.location_id,
                    quantity_change=difference, # quantity_change ใน schema เป็น float
                    reason=f"ปิดรอบตรวจนับสต็อก #{session_id}",
                    notes=(
                        f"ยอดในระบบ: {item.system_quantity}, "
                        f"ยอดนับจริง: {item.counted_quantity}, "
                        f"ส่วนต่าง: {difference:+.2f}" # Format float
                    )
                )
                # เรียกใช้ inventory_service.record_stock_adjustment ที่นี่
                inventory_service.record_stock_adjustment(db=db, adjustment_data=adjustment_data_schema, allow_negative_stock_for_count=True)
                adjustments_created_count += 1

        session.status = models.StockCountStatus.CLOSED
        session.end_date = datetime.utcnow()
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error closing stock count session {session_id}: {type(e).__name__} - {e}")
        if isinstance(e, ValueError): raise e
        else: raise ValueError(f"เกิดข้อผิดพลาดในระบบขณะปิดรอบนับสต็อก: {str(e)}") from e

    db.refresh(session)
    print(f"Stock Count Session {session_id} closed. {adjustments_created_count} adjustments created.")
    return session

def cancel_stock_count_session(db: Session, session_id: int) -> models.StockCountSession:
    session = db.query(models.StockCountSession).filter(models.StockCountSession.id == session_id).with_for_update().first()
    if not session: raise ValueError(f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    if session.status not in [models.StockCountStatus.OPEN, models.StockCountStatus.COUNTING]:
        raise ValueError(f"ไม่สามารถยกเลิกรอบนับที่สถานะ '{session.status.value}' ได้ (ต้องเป็น OPEN หรือ COUNTING)")

    session.status = models.StockCountStatus.CANCELED
    session.end_date = datetime.utcnow()
    try:
        db.commit()
        db.refresh(session)
    except Exception as e:
        db.rollback()
        print(f"DB error canceling session {session_id}: {str(e)}")
        raise ValueError(f"DB error canceling session {session_id}") from e

    print(f"Stock Count Session {session_id} canceled.")
    return session

def add_all_products_from_location_to_session(db: Session, session_id: int) -> Dict[str, Any]:
    session = get_stock_count_session(db, session_id)
    if not session:
        raise ValueError(f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    if not session.location_id:
        raise ValueError(f"รอบนับสต็อก #{session_id} ไม่มีข้อมูลสถานที่")
    if session.status not in [models.StockCountStatus.OPEN, models.StockCountStatus.COUNTING]:
        raise ValueError(f"ไม่สามารถเพิ่มสินค้าในรอบนับที่สถานะ {session.status.value} ได้")

    # ดึง product_id ทั้งหมดที่มีรายการใน CurrentStock ณ สถานที่ของ session นี้
    products_at_location_query = db.query(models.CurrentStock.product_id)\
                                   .filter(models.CurrentStock.location_id == session.location_id)\
                                   .distinct() # เพิ่ม distinct เผื่อมีข้อมูลซ้ำซ้อน (ไม่ควรมีถ้า PK ถูกต้อง)
    
    product_ids_to_add = {pid for (pid,) in products_at_location_query.all()}
    
    # ดึง product_id ที่มีอยู่แล้วใน session นี้ เพื่อป้องกันการเพิ่มซ้ำ
    existing_item_product_ids = {item.product_id for item in session.items}

    added_count = 0
    skipped_count = 0
    errors = []

    for product_id_to_add in product_ids_to_add:
        if product_id_to_add in existing_item_product_ids:
            skipped_count += 1
            continue
        
        try:
            # ตรวจสอบว่า Product ID นั้นมีอยู่จริงในตาราง Products หรือไม่ก่อนเพิ่ม
            product_check = product_service.get_product(db, product_id=product_id_to_add)
            if not product_check:
                errors.append(f"Product ID {product_id_to_add}: ไม่พบข้อมูลสินค้าในระบบ")
                continue

            item_data = schemas.StockCountItemCreate(product_id=product_id_to_add)
            # ใช้ add_product_to_session ที่มีอยู่ ซึ่งจะดึง system_quantity จาก CurrentStock ให้เอง
            add_product_to_session(db, session_id, item_data) 
            added_count += 1
        except ValueError as e:
            errors.append(f"Product ID {product_id_to_add}: {str(e)}")
        except Exception as e:
            db.rollback() # Rollback ถ้าเกิด error ตอนเพิ่มแต่ละรายการ
            errors.append(f"Unexpected error for Product ID {product_id_to_add}: {str(e)}")
            print(f"Rolling back for product {product_id_to_add} due to error: {e}")
    
    # ไม่จำเป็นต้อง commit ที่นี่ถ้า add_product_to_session มีการ commit ภายในตัวมันเอง
    # แต่ถ้า add_product_to_session ไม่ได้ commit ก็ต้อง db.commit() ที่นี่

    return {"added": added_count, "skipped_already_in_session": skipped_count, "errors": errors}