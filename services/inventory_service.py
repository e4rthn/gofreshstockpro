# services/inventory_service.py
from sqlalchemy.orm import Session, joinedload, subqueryload # <--- เพิ่ม subqueryload ที่นี่
from sqlalchemy.sql import func
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Dict, Any, Tuple

# Absolute Imports
from models import (Product, Location, CurrentStock, InventoryTransaction,
                    TransactionType, Category, StockCountSession,
                    StockCountItem, StockCountStatus) # Ensure all used models are imported
import schemas
from schemas.inventory import StockInSchema, StockAdjustmentSchema, StockTransferSchema
from schemas.stock_count import StockCountItemUpdate # Ensure this schema is imported
import models
# Absolute Imports for other services
from services import product_service, location_service

# --- Existing functions (get_current_stock_record, record_stock_in, get_current_stock_summary etc.) ---
# Make sure they are present as per your original file.

def get_current_stock_record(db: Session, product_id: int, location_id: int) -> Optional[CurrentStock]:
    """
    Retrieves a current stock record for a given product and location.
    Applies a row-level lock if the database supports it and the ORM is configured for it.
    """
    return db.query(CurrentStock).filter(
        CurrentStock.product_id == product_id,
        CurrentStock.location_id == location_id
    ).with_for_update().first()


def record_stock_deduction(
    db: Session,
    transaction_type: models.TransactionType,
    product_id: int,
    location_id: int,
    quantity: int, # Positive integer representing the quantity to deduct
    related_transaction_id: Optional[int] = None,
    notes: Optional[str] = None,
    cost_per_unit: Optional[float] = None # Optional: cost associated with this deduction (e.g., for COGS)
) -> models.InventoryTransaction:
    if quantity <= 0:
        raise ValueError("Quantity for stock deduction must be a positive value.")

    # It's good practice to ensure product and location exist, though the caller (e.g., record_sale) might have done this.
    product = product_service.get_product(db, product_id=product_id)
    if not product:
        raise ValueError(f"Product ID {product_id} not found for stock deduction.")
    location = location_service.get_location(db, location_id=location_id)
    if not location:
        raise ValueError(f"Location ID {location_id} not found for stock deduction.")

    # Create the inventory transaction for the deduction
    transaction = models.InventoryTransaction(
        transaction_type=transaction_type,
        product_id=product_id,
        location_id=location_id,
        quantity_change = -abs(quantity), # Ensure it's negative
        related_transaction_id=related_transaction_id,
        notes=notes,
        cost_per_unit=cost_per_unit # Log cost if provided
    )
    db.add(transaction)

    # Update or create CurrentStock record
    current_stock_record = get_current_stock_record(db, product_id=product_id, location_id=location_id)

    if current_stock_record:
        current_stock_record.quantity -= abs(quantity)
        # Note: current_stock_record.last_updated is usually handled by DB (onupdate=func.now())
    else:
        # If no current stock record exists, create one.
        # This deduction will result in a negative initial stock quantity.
        current_stock_record = models.CurrentStock(
            product_id=product_id,
            location_id=location_id,
            quantity = -abs(quantity) # Stock starts negative
        )
        db.add(current_stock_record)

    # The commit will be handled by the calling function (e.g., record_sale)
    # to ensure atomicity of the entire operation.
    # db.flush() could be used here if an ID from transaction or current_stock_record is needed immediately
    # before commit, but typically not necessary for simple deductions.

    return transaction


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

        # For negative adjustments (reducing stock)
        if adjustment_data.quantity_change < 0:
            # If not specifically allowed (e.g., for stock count reconciliation),
            # prevent adjustment from making stock more negative than physical reality dictates,
            # or prevent going below zero if current stock is positive.
            if not allow_negative_stock_for_count:
                if current_quantity_on_hand < abs(adjustment_data.quantity_change):
                    raise ValueError(
                        f"สต็อกไม่เพียงพอสำหรับการปรับลด ปัจจุบัน: {current_quantity_on_hand}, "
                        f"ต้องการลด: {abs(adjustment_data.quantity_change)} ที่ {location.name} สำหรับ '{product.name}'"
                    )
        # For positive adjustments or when negative stock is allowed from count
        transaction_type = TransactionType.ADJUSTMENT_ADD if adjustment_data.quantity_change > 0 else TransactionType.ADJUSTMENT_SUB
        
        transaction_notes = f"เหตุผล: {adjustment_data.reason}" if adjustment_data.reason else "ปรับปรุงสต็อก"
        if adjustment_data.notes:
            transaction_notes += f"; หมายเหตุ: {adjustment_data.notes}"

        # Cost per unit for adjustments might be complex.
        # If it's an adjustment ADD, it might have a cost. If SUB, cost might be based on current average or standard.
        # For simplicity, this example doesn't automatically fetch/calculate cost for adjustments unless provided.
        cost_for_transaction = None # Or fetch/calculate if needed

        transaction = InventoryTransaction(
            transaction_type=transaction_type,
            product_id=adjustment_data.product_id,
            location_id=adjustment_data.location_id,
            quantity_change=adjustment_data.quantity_change,
            notes=transaction_notes,
            cost_per_unit=cost_for_transaction # Pass if available/relevant
        )
        db.add(transaction)

        if current_stock:
            current_stock.quantity += adjustment_data.quantity_change
        else:
            # If no stock record, create one.
            # This is valid if quantity_change is positive, or if negative is allowed (from stock count)
            if adjustment_data.quantity_change > 0 or allow_negative_stock_for_count:
                current_stock = CurrentStock(
                    product_id=adjustment_data.product_id,
                    location_id=adjustment_data.location_id,
                    quantity=adjustment_data.quantity_change
                )
                db.add(current_stock)
            else:
                # This case should ideally be caught by the check above if allow_negative_stock_for_count is False
                raise ValueError("ไม่สามารถปรับปรุงยอดติดลบสำหรับสต็อกที่ยังไม่มีได้ (ยกเว้นกรณีมาจากการนับสต็อก)")
        
        db.commit() # Commit the adjustment transaction and current stock update
        db.refresh(transaction) # Refresh to get DB-generated values like ID, transaction_date
        if current_stock:
            db.refresh(current_stock)
    except Exception as e:
        db.rollback()
        print(f"Error during stock adjustment: {type(e).__name__} - {e}")
        if isinstance(e, ValueError):
            raise e
        else:
            raise ValueError(f"เกิดข้อผิดพลาดในระบบขณะปรับปรุงสต็อก: {type(e).__name__}") from e
    return transaction

# --- Other functions like record_stock_in, get_current_stock_summary,
# get_near_expiry_transactions, record_stock_transfer,
# and stock count related functions (update_counted_quantity, start_counting_session,
# close_stock_count_session, cancel_stock_count_session) should remain here as per your original file.
# Ensure they are compatible with the changes made, particularly around how CurrentStock is handled.

# Placeholder for other inventory service functions from your project
# ...

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
        if current_stock: current_stock.quantity += stock_in_data.quantity
        else:
            current_stock = CurrentStock(product_id=stock_in_data.product_id, location_id=stock_in_data.location_id, quantity=stock_in_data.quantity)
            db.add(current_stock)
        db.commit()
        db.refresh(transaction)
        if current_stock: db.refresh(current_stock)
    except Exception as e:
        db.rollback(); print(f"Error: {e}"); raise ValueError(f"DB error in stock in") from e
    return transaction

def get_current_stock_summary(db: Session, skip: int = 0, limit: int = 100) -> Dict[str, Any]:
    query = db.query(CurrentStock).options(
        joinedload(CurrentStock.product).joinedload(Product.category),
        joinedload(CurrentStock.location))
    total_count = query.count()
    stock_data = query.order_by(CurrentStock.location_id, CurrentStock.product_id).offset(skip).limit(limit).all()
    return {"items": stock_data, "total_count": total_count}

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
        InventoryTransaction.expiry_date != None,
        InventoryTransaction.expiry_date >= today, # Stock that is not yet expired
        InventoryTransaction.expiry_date <= expiry_threshold_date # And will expire within the threshold
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

    try:
        # Lock stock records for both locations to prevent race conditions
        from_stock = get_current_stock_record(db, product_id=transfer_data.product_id, location_id=transfer_data.from_location_id)
        # We get to_stock also with lock in case multiple transfers are happening to the same destination.
        to_stock = get_current_stock_record(db, product_id=transfer_data.product_id, location_id=transfer_data.to_location_id)

        from_quantity_on_hand = from_stock.quantity if from_stock else 0
        if from_quantity_on_hand < transfer_data.quantity:
            raise ValueError(
                f"สต็อกที่ '{from_location.name}' ไม่เพียงพอสำหรับ '{product.name}'. "
                f"ต้องการ: {transfer_data.quantity}, มีอยู่: {from_quantity_on_hand}"
            )

        notes_out = f"โอนย้ายไปที่: {to_location.name} (ID: {to_location.id})"
        notes_in = f"รับโอนจาก: {from_location.name} (ID: {from_location.id})"
        if transfer_data.notes:
            notes_out += f"; หมายเหตุ: {transfer_data.notes}"
            notes_in += f"; หมายเหตุ: {transfer_data.notes}"
        
        # For transfers, cost_per_unit might be carried over or be based on current average cost.
        # This example assumes no specific cost is set for the transfer transaction itself,
        # but it could be enhanced to pass product.standard_cost or average cost.
        cost_for_transfer_tx = from_stock.product.standard_cost if from_stock and from_stock.product else None


        tx_out = InventoryTransaction(
            transaction_type=TransactionType.TRANSFER_OUT,
            product_id=transfer_data.product_id,
            location_id=transfer_data.from_location_id,
            quantity_change= -abs(transfer_data.quantity),
            notes=notes_out,
            cost_per_unit=cost_for_transfer_tx # Log cost
        )
        db.add(tx_out)

        tx_in = InventoryTransaction(
            transaction_type=TransactionType.TRANSFER_IN,
            product_id=transfer_data.product_id,
            location_id=transfer_data.to_location_id,
            quantity_change= abs(transfer_data.quantity),
            notes=notes_in,
            cost_per_unit=cost_for_transfer_tx, # Log the same cost for the receiving transaction
            related_transaction_id=tx_out.id # Link tx_in to tx_out (after tx_out gets an ID)
        )
        # To link tx_in to tx_out.id, we might need to flush tx_out first if IDs are generated on flush.
        # However, SQLAlchemy handles this relationship assignment before commit.
        # For explicit linking, one might do:
        # db.flush() # tx_out gets ID
        # tx_in.related_transaction_id = tx_out.id
        db.add(tx_in)


        # Update CurrentStock
        if from_stock: # Should always exist if quantity check passed
            from_stock.quantity -= abs(transfer_data.quantity)
        # else: This case should be impossible if from_quantity_on_hand was sufficient.

        if to_stock:
            to_stock.quantity += abs(transfer_data.quantity)
        else:
            to_stock = CurrentStock(
                product_id=transfer_data.product_id,
                location_id=transfer_data.to_location_id,
                quantity=abs(transfer_data.quantity)
            )
            db.add(to_stock)
        
        # Link transactions after IDs are available (usually handled by SA relationships or post-flush)
        # For explicit linking via related_transaction_id after flush:
        db.flush() # Ensure IDs are populated if needed for explicit linking
        if tx_out.id and tx_in:
            tx_in.related_transaction_id = tx_out.id # Link them

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
            raise ValueError(f"เกิดข้อผิดพลาดในระบบขณะโอนย้ายสต็อก: {type(e).__name__}") from e
    return tx_out, tx_in


# --- Stock Count Functions (ensure they are complete as in your original file) ---
def update_counted_quantity(db: Session, item_id: int, item_update_data: StockCountItemUpdate) -> StockCountItem:
    db_item = db.query(StockCountItem).options(
        joinedload(StockCountItem.session) # Join session to check its status
    ).filter(StockCountItem.id == item_id).first() # Removed with_for_update for now, lock at session level if needed

    if not db_item:
        raise ValueError(f"ไม่พบรายการตรวจนับ รหัส {item_id}")

    # Lock the session if changing its state or if high concurrency on items is an issue
    # session_to_lock = db.query(StockCountSession).filter(StockCountSession.id == db_item.session_id).with_for_update().first()
    # if not session_to_lock:
    #     raise ValueError(f"Session {db_item.session_id} not found for locking.")
    # db_item.session = session_to_lock # Re-associate with the locked session object

    if db_item.session.status == StockCountStatus.OPEN:
        db_item.session.status = StockCountStatus.COUNTING # Auto-transition to COUNTING
        # db.add(db_item.session) # SA tracks changes, explicit add not always needed if object is managed
    elif db_item.session.status != StockCountStatus.COUNTING:
        raise ValueError(
            f"ไม่สามารถบันทึกยอดนับในรอบนับที่สถานะ '{db_item.session.status.value}' ได้ (ต้องเป็น OPEN หรือ COUNTING)"
        )

    db_item.counted_quantity = item_update_data.counted_quantity
    db_item.count_date = datetime.utcnow() # Or timezone aware: datetime.now(timezone.utc)

    try:
        db.commit()
        db.refresh(db_item)
        if db_item.session: # Refresh the session if it was modified
            db.refresh(db_item.session)
    except Exception as e:
        db.rollback()
        print(f"Error updating counted quantity for item {item_id}: {e}")
        raise ValueError(f"DB error updating count for item {item_id}") from e
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
        raise ValueError(f"DB error starting count session {session_id}") from e
    return session

def close_stock_count_session(db: Session, session_id: int) -> StockCountSession:
    # Use with_for_update to lock the session row during this critical operation
    session = db.query(StockCountSession).filter(
        StockCountSession.id == session_id
    ).options(
        subqueryload(StockCountSession.items) # Eager load items
    ).with_for_update().first()

    if not session:
        raise ValueError(f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    if session.status != StockCountStatus.COUNTING:
        raise ValueError(f"ไม่สามารถปิดรอบนับที่สถานะ '{session.status.value}' ได้ (ต้องเป็น COUNTING)")

    # Items are already loaded due to subqueryload
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
            difference = item.difference # This is a property on the model
            if difference is not None and difference != 0:
                adjustment_data = schemas.StockAdjustmentSchema(
                    product_id=item.product_id,
                    location_id=session.location_id,
                    quantity_change=difference,
                    reason=f"ปิดรอบตรวจนับสต็อก #{session_id}",
                    notes=(
                        f"ยอดในระบบ: {item.system_quantity}, "
                        f"ยอดนับจริง: {item.counted_quantity}, "
                        f"ส่วนต่าง: {difference:+}" # Show sign for difference
                    )
                )
                # Call record_stock_adjustment from the same service
                # allow_negative_stock_for_count=True allows stock to go negative based on count results
                record_stock_adjustment(db=db, adjustment_data=adjustment_data, allow_negative_stock_for_count=True)
                adjustments_created_count += 1
        
        session.status = StockCountStatus.CLOSED
        session.end_date = datetime.utcnow() # Or timezone.utc
        
        db.commit() # Single commit for all changes (session status, items, adjustments)
    except Exception as e:
        db.rollback()
        print(f"Error closing stock count session {session_id}: {type(e).__name__} - {e}")
        if isinstance(e, ValueError): # if record_stock_adjustment raised a ValueError specific to its logic
            raise e
        else: # For other DB errors or unexpected issues
            raise ValueError(f"เกิดข้อผิดพลาดในระบบขณะปิดรอบนับสต็อก: {type(e).__name__}") from e
            
    db.refresh(session) # Refresh to get updated state
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
    session.end_date = datetime.utcnow() # Or timezone.utc
    try:
        db.commit()
        db.refresh(session)
    except Exception as e:
        db.rollback()
        print(f"Error canceling stock count session {session_id}: {e}")
        raise ValueError(f"DB error canceling session {session_id}") from e
        
    print(f"Stock Count Session {session_id} canceled.")
    return session