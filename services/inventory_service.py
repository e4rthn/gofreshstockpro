# services/inventory_service.py
from sqlalchemy.orm import Session, joinedload, subqueryload
from sqlalchemy.sql import func
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Dict, Any, Tuple

# Absolute Imports
from models import (Product, Location, CurrentStock, InventoryTransaction,
                    TransactionType, Category, StockCountSession,
                    StockCountItem, StockCountStatus)
import schemas
from schemas.inventory import StockInSchema, StockAdjustmentSchema, StockTransferSchema
from schemas.stock_count import StockCountItemUpdate
import models # Ensure models is imported if used like models.TransactionType etc.

# Absolute Imports for other services
from services import product_service, location_service

# --- Existing functions (get_current_stock_record, record_stock_in, etc.) ---
# ... (โค้ดฟังก์ชันอื่นๆ ของคุณอยู่ที่นี่ ไม่ต้องแก้ไข) ...

def get_current_stock_record(db: Session, product_id: int, location_id: int) -> Optional[CurrentStock]:
    """ ดึงข้อมูล CurrentStock record พร้อม lock for update """
    return db.query(CurrentStock).filter(
        CurrentStock.product_id == product_id,
        CurrentStock.location_id == location_id
    ).with_for_update().first()

def record_stock_in(db: Session, stock_in_data: StockInSchema) -> InventoryTransaction:
    product = product_service.get_product(db, product_id=stock_in_data.product_id)
    if not product: raise ValueError(f"ไม่พบสินค้า รหัส {stock_in_data.product_id}")
    location = location_service.get_location(db, location_id=stock_in_data.location_id)
    if not location: raise ValueError(f"ไม่พบสถานที่จัดเก็บ รหัส {stock_in_data.location_id}")
    try:
        transaction = InventoryTransaction(
            transaction_type=TransactionType.STOCK_IN, product_id=stock_in_data.product_id,
            location_id=stock_in_data.location_id, quantity_change=stock_in_data.quantity,
            cost_per_unit=stock_in_data.cost_per_unit, expiry_date=stock_in_data.expiry_date,
            notes=stock_in_data.notes
        )
        db.add(transaction)
        current_stock = get_current_stock_record(db, product_id=stock_in_data.product_id, location_id=stock_in_data.location_id)
        if current_stock:
            current_stock.quantity += stock_in_data.quantity
        else:
            current_stock = CurrentStock(product_id=stock_in_data.product_id, location_id=stock_in_data.location_id, quantity=stock_in_data.quantity)
            db.add(current_stock)
        db.commit()
        db.refresh(transaction)
        if current_stock:
             db.refresh(current_stock)
    except Exception as e:
        db.rollback()
        print(f"Error in record_stock_in: {type(e).__name__} - {e}")
        raise ValueError(f"DB error in stock in: {str(e)}") from e
    return transaction

def get_current_stock_summary(db: Session,
                              skip: int = 0,
                              limit: int = 100,
                              category_id: Optional[int] = None,
                              location_id: Optional[int] = None) -> Dict[str, Any]:
    query = db.query(CurrentStock).options(
        joinedload(CurrentStock.product).joinedload(Product.category),
        joinedload(CurrentStock.location)
    )

    if category_id is not None:
        query = query.join(Product, CurrentStock.product_id == Product.id).filter(Product.category_id == category_id)

    if location_id is not None:
        query = query.filter(CurrentStock.location_id == location_id)

    total_count = query.count()

    order_expressions = []
    if location_id is None:
         # Order by location name using the relationship
        query = query.outerjoin(Location, CurrentStock.location_id == Location.id) # Ensure join if not implicitly done by options
        order_expressions.append(Location.name)

    # Order by product name using the relationship
    query = query.outerjoin(Product, CurrentStock.product_id == Product.id) # Ensure join if not implicitly done by options
    order_expressions.append(Product.name)


    stock_data = query.order_by(*order_expressions).offset(skip).limit(limit).all()
    return {"items": stock_data, "total_count": total_count}


def record_stock_adjustment(db: Session, adjustment_data: StockAdjustmentSchema, allow_negative_stock_for_count: bool = False) -> InventoryTransaction:
    if adjustment_data.quantity_change == 0:
        raise ValueError("จำนวนที่เปลี่ยนแปลงต้องไม่เป็นศูนย์")

    product = product_service.get_product(db, product_id=adjustment_data.product_id)
    if not product:
        raise ValueError(f"ไม่พบสินค้า รหัส {adjustment_data.product_id}")
    location = location_service.get_location(db, location_id=adjustment_data.location_id)
    if not location:
        raise ValueError(f"ไม่พบสถานที่จัดเก็บ รหัส {adjustment_data.location_id}")

    try:
        current_stock = get_current_stock_record(db, product_id=adjustment_data.product_id, location_id=adjustment_data.location_id)
        current_quantity_on_hand = current_stock.quantity if current_stock else 0

        if adjustment_data.quantity_change < 0:
            if not allow_negative_stock_for_count: # Check the flag
                if current_quantity_on_hand < abs(adjustment_data.quantity_change):
                    raise ValueError(
                        f"สต็อกไม่เพียงพอสำหรับการปรับลด ปัจจุบัน: {current_quantity_on_hand}, "
                        f"ต้องการลด: {abs(adjustment_data.quantity_change)} ที่ {location.name} สำหรับ '{product.name}'"
                    )

        transaction_type = TransactionType.ADJUSTMENT_ADD if adjustment_data.quantity_change > 0 else TransactionType.ADJUSTMENT_SUB

        transaction_notes = f"เหตุผล: {adjustment_data.reason}" if adjustment_data.reason else "ปรับปรุงสต็อก"
        if adjustment_data.notes:
            transaction_notes += f"; หมายเหตุ: {adjustment_data.notes}"

        transaction = InventoryTransaction(
            transaction_type=transaction_type,
            product_id=adjustment_data.product_id,
            location_id=adjustment_data.location_id,
            quantity_change=adjustment_data.quantity_change,
            notes=transaction_notes
        )
        db.add(transaction)

        if current_stock:
            current_stock.quantity += adjustment_data.quantity_change
        else:
             current_stock = CurrentStock(
                product_id=adjustment_data.product_id,
                location_id=adjustment_data.location_id,
                quantity=adjustment_data.quantity_change
            )
             db.add(current_stock)

        db.commit()
        db.refresh(transaction)
        if current_stock:
            db.refresh(current_stock)

    except Exception as e:
        db.rollback()
        print(f"Error during stock adjustment: {type(e).__name__} - {e}")
        if isinstance(e, ValueError):
            raise e
        else:
            raise ValueError(f"เกิดข้อผิดพลาดในระบบขณะปรับปรุงสต็อก: {str(e)}") from e
    return transaction

def record_stock_deduction(
    db: Session,
    transaction_type: TransactionType,
    product_id: int,
    location_id: int,
    quantity: int,
    related_transaction_id: Optional[int] = None,
    notes: Optional[str] = None,
    cost_per_unit: Optional[float] = None
) -> InventoryTransaction:
    if quantity <= 0:
        raise ValueError("Quantity for stock deduction must be a positive value.")

    transaction = InventoryTransaction(
        transaction_type=transaction_type,
        product_id=product_id,
        location_id=location_id,
        quantity_change = -abs(quantity),
        related_transaction_id=related_transaction_id,
        notes=notes,
        cost_per_unit=cost_per_unit
    )
    db.add(transaction)

    current_stock_record = get_current_stock_record(db, product_id=product_id, location_id=location_id)
    if current_stock_record:
        current_stock_record.quantity -= abs(quantity)
    else:
        current_stock_record = CurrentStock(
            product_id=product_id,
            location_id=location_id,
            quantity = -abs(quantity)
        )
        db.add(current_stock_record)
    return transaction

def get_near_expiry_transactions(
    db: Session, days_ahead: int = 30, skip: int = 0, limit: int = 100
) -> Dict[str, Any]:
    today = date.today()
    expiry_threshold_date = today + timedelta(days=days_ahead)
    query = db.query(InventoryTransaction).options(
        joinedload(InventoryTransaction.product).joinedload(Product.category),
        joinedload(InventoryTransaction.location)
    ).filter(
        InventoryTransaction.transaction_type == TransactionType.STOCK_IN,
        InventoryTransaction.expiry_date.isnot(None),
        InventoryTransaction.expiry_date >= today,
        InventoryTransaction.expiry_date <= expiry_threshold_date
    )
    total_count = query.count()
    transactions_data = query.order_by(InventoryTransaction.expiry_date.asc()).offset(skip).limit(limit).all()
    return {"transactions": transactions_data, "total_count": total_count}

def record_stock_transfer(
    db: Session, transfer_data: StockTransferSchema
) -> Tuple[InventoryTransaction, InventoryTransaction]:
    if transfer_data.quantity <= 0: raise ValueError("จำนวนที่โอนย้ายต้องมากกว่าศูนย์")

    product = product_service.get_product(db, product_id=transfer_data.product_id)
    if not product: raise ValueError(f"ไม่พบสินค้า รหัส {transfer_data.product_id}")

    from_location = location_service.get_location(db, location_id=transfer_data.from_location_id)
    if not from_location: raise ValueError(f"ไม่พบสถานที่จัดเก็บต้นทาง รหัส {transfer_data.from_location_id}")

    to_location = location_service.get_location(db, location_id=transfer_data.to_location_id)
    if not to_location: raise ValueError(f"ไม่พบสถานที่จัดเก็บปลายทาง รหัส {transfer_data.to_location_id}")

    if transfer_data.from_location_id == transfer_data.to_location_id:
        raise ValueError("สถานที่จัดเก็บต้นทางและปลายทางต้องแตกต่างกัน")

    tx_out = None
    tx_in = None
    try:
        from_stock = get_current_stock_record(db, product_id=transfer_data.product_id, location_id=transfer_data.from_location_id)
        to_stock = get_current_stock_record(db, product_id=transfer_data.product_id, location_id=transfer_data.to_location_id)

        from_quantity_on_hand = from_stock.quantity if from_stock else 0
        if from_quantity_on_hand < transfer_data.quantity:
            raise ValueError(
                f"สต็อกที่ '{from_location.name}' ไม่เพียงพอสำหรับ '{product.name}'. "
                f"ต้องการ: {transfer_data.quantity}, มีอยู่: {from_quantity_on_hand}"
            )

        notes_out_detail = f"โอนย้ายไปที่: {to_location.name} (ID: {to_location.id})"
        notes_in_detail = f"รับโอนจาก: {from_location.name} (ID: {from_location.id})"
        if transfer_data.notes:
            notes_out_detail += f"; หมายเหตุ: {transfer_data.notes}"
            notes_in_detail += f"; หมายเหตุ: {transfer_data.notes}"

        cost_for_transfer_tx = product.standard_cost

        tx_out = InventoryTransaction(
            transaction_type=TransactionType.TRANSFER_OUT, product_id=transfer_data.product_id,
            location_id=transfer_data.from_location_id, quantity_change= -abs(transfer_data.quantity),
            notes=notes_out_detail, cost_per_unit=cost_for_transfer_tx
        )
        db.add(tx_out)
        db.flush()

        tx_in = InventoryTransaction(
            transaction_type=TransactionType.TRANSFER_IN, product_id=transfer_data.product_id,
            location_id=transfer_data.to_location_id, quantity_change= abs(transfer_data.quantity),
            notes=notes_in_detail, cost_per_unit=cost_for_transfer_tx,
            related_transaction_id=tx_out.id
        )
        db.add(tx_in)

        if from_stock:
            from_stock.quantity -= abs(transfer_data.quantity)

        if to_stock:
            to_stock.quantity += abs(transfer_data.quantity)
        else:
            to_stock = CurrentStock(
                product_id=transfer_data.product_id,
                location_id=transfer_data.to_location_id,
                quantity=abs(transfer_data.quantity)
            )
            db.add(to_stock)

        db.commit()
        db.refresh(tx_out); db.refresh(tx_in)
        if from_stock: db.refresh(from_stock)
        if to_stock: db.refresh(to_stock)

    except Exception as e:
        db.rollback()
        print(f"Error during stock transfer: {type(e).__name__} - {e}")
        if isinstance(e, ValueError):
            raise e
        else:
            raise ValueError(f"เกิดข้อผิดพลาดในระบบขณะโอนย้ายสต็อก: {str(e)}") from e

    if tx_out is None or tx_in is None:
        raise RuntimeError("Failed to create transfer transactions.")

    return tx_out, tx_in

def update_counted_quantity(db: Session, item_id: int, item_update_data: StockCountItemUpdate) -> StockCountItem:
    db_item = db.query(StockCountItem).options(
        joinedload(StockCountItem.session)
    ).filter(StockCountItem.id == item_id).with_for_update().first()

    if not db_item:
        raise ValueError(f"ไม่พบรายการตรวจนับ รหัส {item_id}")

    session = db.query(StockCountSession).filter(StockCountSession.id == db_item.session_id).with_for_update().first()
    if not session:
         raise ValueError(f"Session associated with item {item_id} not found.")

    if session.status == StockCountStatus.OPEN:
        session.status = StockCountStatus.COUNTING
    elif session.status != StockCountStatus.COUNTING:
        raise ValueError(
            f"ไม่สามารถบันทึกยอดนับในรอบนับที่สถานะ '{session.status.value}' ได้ (ต้องเป็น OPEN หรือ COUNTING)"
        )

    db_item.counted_quantity = item_update_data.counted_quantity
    db_item.count_date = datetime.utcnow()

    try:
        db.commit()
        db.refresh(db_item)
        db.refresh(session)
    except Exception as e:
        db.rollback()
        raise ValueError(f"DB error updating count for item {item_id}: {str(e)}") from e
    return db_item

def start_counting_session(db: Session, session_id: int) -> StockCountSession:
    session = db.query(StockCountSession).filter(StockCountSession.id == session_id).with_for_update().first()
    if not session:
        raise ValueError(f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    if session.status != StockCountStatus.OPEN:
        raise ValueError(f"รอบนับนี้ไม่ได้อยู่ในสถานะ OPEN (สถานะปัจจุบัน: {session.status.value})")

    session.status = StockCountStatus.COUNTING
    try:
        db.commit()
        db.refresh(session)
    except Exception as e:
        db.rollback()
        raise ValueError(f"DB error starting count session {session_id}: {str(e)}") from e
    return session

def close_stock_count_session(db: Session, session_id: int) -> StockCountSession:
    session = db.query(StockCountSession).options(
        subqueryload(StockCountSession.items)
    ).filter(StockCountSession.id == session_id).with_for_update().first()

    if not session:
        raise ValueError(f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    if session.status != StockCountStatus.COUNTING:
        raise ValueError(f"ไม่สามารถปิดรอบนับที่สถานะ '{session.status.value}' ได้ (ต้องเป็น COUNTING)")

    items_in_session = session.items
    uncounted_items = [item for item in items_in_session if item.counted_quantity is None]
    if uncounted_items:
        product_ids_str = ", ".join(str(item.product_id) for item in uncounted_items)
        raise ValueError(
            f"กรุณาบันทึกยอดนับให้ครบทุกรายการก่อนปิดรอบนับ (สินค้า ID ที่ยังไม่ได้นับ: {product_ids_str})"
        )

    try:
        adjustments_created_count = 0
        for item in items_in_session:
            difference = item.difference
            if difference is not None and difference != 0:
                adjustment_data_schema = schemas.StockAdjustmentSchema(
                    product_id=item.product_id,
                    location_id=session.location_id,
                    quantity_change=difference,
                    reason=f"ปิดรอบตรวจนับสต็อก #{session_id}",
                    notes=(
                        f"ยอดในระบบ: {item.system_quantity}, "
                        f"ยอดนับจริง: {item.counted_quantity}, "
                        f"ส่วนต่าง: {difference:+}"
                    )
                )
                record_stock_adjustment(db=db, adjustment_data=adjustment_data_schema, allow_negative_stock_for_count=True)
                adjustments_created_count += 1

        session.status = StockCountStatus.CLOSED
        session.end_date = datetime.utcnow()

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error closing stock count session {session_id}: {type(e).__name__} - {e}")
        if isinstance(e, ValueError):
            raise e
        else:
            raise ValueError(f"เกิดข้อผิดพลาดในระบบขณะปิดรอบนับสต็อก: {str(e)}") from e

    db.refresh(session)
    print(f"Stock Count Session {session_id} closed. {adjustments_created_count} adjustments created.")
    return session

def cancel_stock_count_session(db: Session, session_id: int) -> StockCountSession:
    session = db.query(StockCountSession).filter(StockCountSession.id == session_id).with_for_update().first()
    if not session:
        raise ValueError(f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    if session.status not in [StockCountStatus.OPEN, StockCountStatus.COUNTING]:
        raise ValueError(
            f"ไม่สามารถยกเลิกรอบนับที่สถานะ '{session.status.value}' ได้ (ต้องเป็น OPEN หรือ COUNTING)"
        )

    session.status = StockCountStatus.CANCELED
    session.end_date = datetime.utcnow()
    try:
        db.commit()
        db.refresh(session)
    except Exception as e:
        db.rollback()
        raise ValueError(f"DB error canceling session {session_id}: {str(e)}") from e

    print(f"Stock Count Session {session_id} canceled.")
    return session

# --- Negative Stock Report Function (Updated ORDER BY) ---
def get_negative_stock_items(
    db: Session,
    location_id: Optional[int] = None,
    category_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100
) -> Dict[str, Any]:
    """
    ดึงรายการสินค้าที่มีสต็อกติดลบ (quantity < 0) พร้อมข้อมูลที่เกี่ยวข้อง
    รองรับการกรองตามสถานที่และหมวดหมู่ และการแบ่งหน้า
    """
    query = db.query(models.CurrentStock).options(
        joinedload(models.CurrentStock.product).joinedload(models.Product.category),
        joinedload(models.CurrentStock.location)
    ).filter(models.CurrentStock.quantity < 0)

    if location_id is not None:
        query = query.filter(models.CurrentStock.location_id == location_id)

    if category_id is not None:
        query = query.join(models.Product, models.CurrentStock.product_id == models.Product.id)\
                     .filter(models.Product.category_id == category_id)

    # --- Counting ---
    try:
        total_count = query.count()
    except Exception as e:
        print(f"Warning: Complex count failed ({e}), attempting simpler count.")
        count_query = db.query(func.count(models.CurrentStock.id)).filter(models.CurrentStock.quantity < 0)
        if location_id is not None:
             count_query = count_query.filter(models.CurrentStock.location_id == location_id)
        if category_id is not None:
            count_query = count_query.join(models.Product, models.CurrentStock.product_id == models.Product.id)\
                                    .filter(models.Product.category_id == category_id)
        total_count = count_query.scalar() or 0

    # --- Ordering and Pagination (Corrected ORDER BY) ---
    # Order by location name (via relationship), then product name (via relationship)
    items: List[models.CurrentStock] = query.order_by(
                                            models.Location.name,  # Order using the joined Location model's name
                                            models.Product.name    # Order using the joined Product model's name
                                         )\
                                         .offset(skip).limit(limit).all()
    # Note: Ensure Location and Product are properly joined either via `options(joinedload(...))`
    # or explicit `.join()` if ordering based on them. The joinedload should handle this.

    return {"items": items, "total_count": total_count}
# -------------------------------------------

# ... (Rest of your inventory_service.py, if any) ...