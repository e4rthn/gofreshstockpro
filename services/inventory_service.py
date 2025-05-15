
from sqlalchemy.orm import Session, joinedload, subqueryload, defer, selectinload #<-- เพิ่ม selectinload
from sqlalchemy import func, distinct, desc, cast, Date as SQLDate, or_, and_
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Dict, Any, Tuple

# Absolute Imports
from models import (Product, Location, CurrentStock, InventoryTransaction,
                    TransactionType, Category, StockCountSession,
                    StockCountItem, StockCountStatus, SaleItem)
import schemas
# Import specific schemas needed
from schemas.inventory import StockInSchema, StockAdjustmentSchema, StockTransferSchema
from schemas.stock_count import StockCountItemUpdate

# Absolute Imports for other services
from services import product_service, location_service

# --- Existing functions (get_current_stock_record, record_stock_in, get_current_stock_summary, etc.) ---
def get_current_stock_record(db: Session, product_id: int, location_id: int) -> Optional[CurrentStock]:
    """ ดึงข้อมูล CurrentStock ของสินค้าและสถานที่ที่ระบุ (พร้อม Lock สำหรับ Update) """
    return db.query(CurrentStock).filter(
        CurrentStock.product_id == product_id,
        CurrentStock.location_id == location_id
    ).with_for_update().first()

def record_stock_in(db: Session, stock_in_data: schemas.StockInSchema) -> InventoryTransaction:
    """ บันทึกการรับสินค้าเข้า, คำนวณวันหมดอายุ, และอัปเดต CurrentStock """
    product = product_service.get_product(db, product_id=stock_in_data.product_id)
    if not product: raise ValueError(f"ไม่พบสินค้า รหัส {stock_in_data.product_id}")
    location = location_service.get_location(db, location_id=stock_in_data.location_id)
    if not location: raise ValueError(f"ไม่พบสถานที่จัดเก็บ รหัส {stock_in_data.location_id}")

    calculated_expiry_date: Optional[date] = stock_in_data.expiry_date
    if stock_in_data.production_date and product.shelf_life_days is not None and product.shelf_life_days >= 0:
        if calculated_expiry_date: print(f"Warning: Using calculated expiry for product {product.id}.")
        try: calculated_expiry_date = stock_in_data.production_date + timedelta(days=int(product.shelf_life_days))
        except (TypeError, ValueError) as e: raise ValueError("ไม่สามารถคำนวณ Expiry Date ได้")
    elif product.shelf_life_days is not None and product.shelf_life_days >= 0 and not stock_in_data.production_date:
        if not calculated_expiry_date: raise ValueError(f"สินค้า '{product.name}' มี Shelf Life กรุณาระบุ Production Date หรือ Expiry Date โดยตรง")

    try:
        transaction = InventoryTransaction(
            transaction_type=TransactionType.STOCK_IN, product_id=stock_in_data.product_id,
            location_id=stock_in_data.location_id, quantity_change=stock_in_data.quantity,
            cost_per_unit=stock_in_data.cost_per_unit, production_date=stock_in_data.production_date,
            expiry_date=calculated_expiry_date, notes=stock_in_data.notes
        )
        db.add(transaction)
        current_stock = get_current_stock_record(db, product_id=stock_in_data.product_id, location_id=stock_in_data.location_id)
        if current_stock: current_stock.quantity += stock_in_data.quantity
        else:
            current_stock = CurrentStock(product_id=stock_in_data.product_id, location_id=stock_in_data.location_id, quantity=stock_in_data.quantity)
            db.add(current_stock)
        db.commit(); db.refresh(transaction)
        if current_stock: db.refresh(current_stock)
    except Exception as e:
        db.rollback(); print(f"Error in record_stock_in: {type(e).__name__} - {e}")
        if isinstance(e, ValueError): raise e
        else: raise ValueError(f"เกิดข้อผิดพลาดในการบันทึกข้อมูลสต็อกเข้า: {str(e)}") from e
    return transaction

def get_current_stock_summary(db: Session, skip: int = 0, limit: int = 100, category_id: Optional[int] = None, location_id: Optional[int] = None) -> Dict[str, Any]:
    # ... (โค้ดเหมือนเดิม) ...
    query = db.query(CurrentStock).options(selectinload(CurrentStock.product).joinedload(Product.category), selectinload(CurrentStock.location)) # Use selectinload
    if category_id is not None: query = query.join(Product, CurrentStock.product_id == Product.id).filter(Product.category_id == category_id)
    if location_id is not None: query = query.filter(CurrentStock.location_id == location_id)
    total_count = query.count()
    order_expressions = []
    if location_id is None: query = query.join(Location, CurrentStock.location_id == Location.id); order_expressions.append(Location.name)
    if not category_id: query = query.join(Product, CurrentStock.product_id == Product.id, isouter=True)
    order_expressions.append(Product.name)
    stock_data = query.order_by(*order_expressions).offset(skip).limit(limit).all()
    return {"items": stock_data, "total_count": total_count}

# --- *** เพิ่มฟังก์ชันดึง Transaction ทั้งหมด *** ---
def get_inventory_transactions(
    db: Session,
    skip: int = 0,
    limit: int = 30, # Default limit for this page
    product_id: Optional[int] = None,
    location_id: Optional[int] = None,
    transaction_type: Optional[TransactionType] = None, # Accept Enum type
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    ดึงรายการเคลื่อนไหวสต็อกทั้งหมด พร้อม Filter และ Pagination
    """
    query = db.query(InventoryTransaction).options(
        selectinload(InventoryTransaction.product), # Use selectinload for potentially faster loading
        selectinload(InventoryTransaction.location)
    )

    # --- Apply Filters ---
    filters = []
    if product_id is not None:
        filters.append(InventoryTransaction.product_id == product_id)
    if location_id is not None:
        filters.append(InventoryTransaction.location_id == location_id)
    if transaction_type is not None:
        # Ensure comparison is with the Enum member, not just string
        filters.append(InventoryTransaction.transaction_type == transaction_type)
    if start_date:
        start_datetime = datetime.combine(start_date, time.min)
        filters.append(InventoryTransaction.transaction_date >= start_datetime)
    if end_date:
        # Include the whole end date
        end_datetime = datetime.combine(end_date + timedelta(days=1), time.min)
        filters.append(InventoryTransaction.transaction_date < end_datetime)

    if filters:
        query = query.filter(and_(*filters)) # Apply all filters

    # --- Count Total ---
    try:
        total_count = query.count()
    except Exception as count_exc:
        print(f"Error counting transactions: {count_exc}")
        total_count = 0 # Fallback count on error

    # --- Apply Sorting and Pagination ---
    transactions_data = []
    if total_count > 0 : # Only query if count > 0
        transactions_data = query.order_by(
            InventoryTransaction.transaction_date.desc(), # Sort by date descending
            InventoryTransaction.id.desc() # Secondary sort by ID
        ).offset(skip).limit(limit).all()

    return {"items": transactions_data, "total_count": total_count}


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

        if adjustment_data.quantity_change < 0: # If reducing stock
            # Check stock unless it's from a stock count adjustment override
            if not allow_negative_stock_for_count:
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
            # Cost per unit is usually not recorded for adjustments unless it's specific (e.g., write-off value)
        )
        db.add(transaction)

        if current_stock:
            current_stock.quantity += adjustment_data.quantity_change
        else:
            # Only create a new stock record if adding stock or if negative is allowed (stock count)
            if adjustment_data.quantity_change > 0 or allow_negative_stock_for_count:
                current_stock = CurrentStock(
                    product_id=adjustment_data.product_id,
                    location_id=adjustment_data.location_id,
                    quantity=adjustment_data.quantity_change
                )
                db.add(current_stock)
            else:
                # Trying to adjust negatively a product that doesn't exist in stock yet, and not from count
                 raise ValueError("ไม่สามารถปรับปรุงยอดติดลบสำหรับสต็อกที่ยังไม่มีได้ (ยกเว้นกรณีมาจากการนับสต็อก)")

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
    quantity: float,
    related_transaction_id: Optional[int] = None,
    notes: Optional[str] = None,
    cost_per_unit: Optional[float] = None # Allow passing cost if needed (e.g., from product standard cost)
) -> InventoryTransaction:
    """ Helper to record a negative stock change (e.g., Sale, Transfer Out) """
    if quantity <= 0:
        raise ValueError("Quantity for stock deduction must be a positive value.")

    transaction = InventoryTransaction(
        transaction_type=transaction_type,
        product_id=product_id,
        location_id=location_id,
        quantity_change = -abs(quantity), # Ensure it's negative
        related_transaction_id=related_transaction_id,
        notes=notes,
        cost_per_unit=cost_per_unit # Record cost if provided
    )
    db.add(transaction)

    current_stock_record = get_current_stock_record(db, product_id=product_id, location_id=location_id)
    if current_stock_record:
        current_stock_record.quantity -= abs(quantity)
    else:
        # If no current stock record exists, creating one with negative quantity
        # This handles cases where sales override allows selling non-existent stock
        print(f"Warning: Deducting stock for non-existent record (Product ID: {product_id}, Location ID: {location_id}). Creating negative stock record.")
        current_stock_record = CurrentStock(
            product_id=product_id,
            location_id=location_id,
            quantity = -abs(quantity)
        )
        db.add(current_stock_record)
    # The commit should be handled by the calling function (e.g., record_sale, record_stock_transfer)
    return transaction


def get_near_expiry_transactions(
    db: Session, days_ahead: int = 30, skip: int = 0, limit: int = 100
) -> Dict[str, Any]:
    """ ดึงรายการ Stock In ที่ใกล้หมดอายุ """
    today = date.today()
    expiry_threshold_date = today + timedelta(days=days_ahead)

    query = db.query(InventoryTransaction).options(
        joinedload(InventoryTransaction.product).joinedload(Product.category),
        joinedload(InventoryTransaction.location)
    ).filter(
        InventoryTransaction.transaction_type == TransactionType.STOCK_IN,
        InventoryTransaction.expiry_date.isnot(None),
        InventoryTransaction.expiry_date >= today, # Start from today
        InventoryTransaction.expiry_date <= expiry_threshold_date # Up to threshold date
    )

    total_count = query.count()
    transactions_data = query.order_by(InventoryTransaction.expiry_date.asc()).offset(skip).limit(limit).all()
    return {"transactions": transactions_data, "total_count": total_count}


def record_stock_transfer(
    db: Session, transfer_data: StockTransferSchema
) -> Tuple[InventoryTransaction, InventoryTransaction]:
    """ บันทึกการโอนย้ายสต็อกระหว่างสถานที่ """
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
        # Lock both stock records if they exist
        from_stock = get_current_stock_record(db, product_id=transfer_data.product_id, location_id=transfer_data.from_location_id)
        to_stock = get_current_stock_record(db, product_id=transfer_data.product_id, location_id=transfer_data.to_location_id)

        from_quantity_on_hand = from_stock.quantity if from_stock else 0
        if from_quantity_on_hand < transfer_data.quantity:
            raise ValueError(
                f"สต็อกที่ '{from_location.name}' ไม่เพียงพอสำหรับ '{product.name}'. "
                f"ต้องการ: {transfer_data.quantity}, มีอยู่: {from_quantity_on_hand}"
            )

        # Prepare notes
        notes_out_detail = f"โอนย้ายไปที่: {to_location.name} (ID: {to_location.id})"
        notes_in_detail = f"รับโอนจาก: {from_location.name} (ID: {from_location.id})"
        if transfer_data.notes:
            notes_out_detail += f"; หมายเหตุ: {transfer_data.notes}"
            notes_in_detail += f"; หมายเหตุ: {transfer_data.notes}"

        # Use standard cost for the transaction value (optional)
        cost_for_transfer_tx = product.standard_cost

        # Create TRANSFER_OUT transaction
        tx_out = InventoryTransaction(
            transaction_type=TransactionType.TRANSFER_OUT,
            product_id=transfer_data.product_id,
            location_id=transfer_data.from_location_id,
            quantity_change= -abs(transfer_data.quantity),
            notes=notes_out_detail,
            cost_per_unit=cost_for_transfer_tx
        )
        db.add(tx_out)
        db.flush() # Flush to get tx_out.id for related_transaction_id

        # Create TRANSFER_IN transaction
        tx_in = InventoryTransaction(
            transaction_type=TransactionType.TRANSFER_IN,
            product_id=transfer_data.product_id,
            location_id=transfer_data.to_location_id,
            quantity_change= abs(transfer_data.quantity),
            notes=notes_in_detail,
            cost_per_unit=cost_for_transfer_tx,
            related_transaction_id=tx_out.id # Link TRANSFER_IN to TRANSFER_OUT
        )
        db.add(tx_in)

        # Update source stock (must exist due to check above)
        if from_stock:
            from_stock.quantity -= abs(transfer_data.quantity)
        # else: # Should not happen due to the check earlier
        #    raise RuntimeError("Source stock vanished during transfer operation.")

        # Update destination stock (create if not exists)
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

    # Check if transactions were successfully created (should not be None after commit)
    if tx_out is None or tx_in is None:
        # This would indicate a serious issue if commit succeeded but objects are None
        raise RuntimeError("Failed to create transfer transactions despite commit apparently succeeding.")

    return tx_out, tx_in

# --- Stock Count Related Functions (moved from stock_count_service for consolidation, if desired) ---
# Or keep them in stock_count_service and call inventory_service.record_stock_adjustment from there.
# Assuming they remain here for now:

def update_counted_quantity(db: Session, item_id: int, item_update_data: StockCountItemUpdate) -> StockCountItem:
    """ อัปเดตยอดนับจริงของรายการในรอบนับ (ใช้ภายใน inventory_service หรือ stock_count_service) """
    # Use with_for_update() if locking the item during update is desired
    db_item = db.query(StockCountItem).options(
        joinedload(StockCountItem.session) # Need session to check status
    ).filter(StockCountItem.id == item_id).with_for_update().first()

    if not db_item:
        raise ValueError(f"ไม่พบรายการตรวจนับ รหัส {item_id}")

    # Check session status before allowing count update
    if db_item.session.status == StockCountStatus.OPEN:
        # Automatically change status to COUNTING when first count is entered
        print(f"Stock Count Session {db_item.session.id} status changed from OPEN to COUNTING.")
        db_item.session.status = StockCountStatus.COUNTING
        # No need to add session again if relationship handles updates, but explicit can be safer
        # db.add(db_item.session)
    elif db_item.session.status != StockCountStatus.COUNTING:
        raise ValueError(
            f"ไม่สามารถบันทึกยอดนับในรอบนับที่สถานะ '{db_item.session.status.value}' ได้ (ต้องเป็น OPEN หรือ COUNTING)"
        )

    # Update counted quantity and date
    db_item.counted_quantity = item_update_data.counted_quantity
    db_item.count_date = datetime.utcnow()

    try:
        db.commit() # Commit changes to item and potentially session status
        db.refresh(db_item)
        if db_item.session:
            db.refresh(db_item.session) # Refresh session to get updated status if changed
    except Exception as e:
        db.rollback()
        print(f"DB error updating count for item {item_id}: {str(e)}")
        raise ValueError(f"DB error updating count for item {item_id}") from e # Re-raise as ValueError
    return db_item

def start_counting_session(db: Session, session_id: int) -> StockCountSession:
    """ เปลี่ยนสถานะรอบนับเป็น COUNTING (ใช้ภายใน inventory_service หรือ stock_count_service) """
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
        print(f"DB error starting count session {session_id}: {str(e)}")
        raise ValueError(f"DB error starting count session {session_id}") from e
    return session

def close_stock_count_session(db: Session, session_id: int) -> StockCountSession:
    """ ปิดรอบนับสต็อก และสร้าง Stock Adjustment สำหรับส่วนต่าง (ใช้ภายใน inventory_service หรือ stock_count_service) """
    # Eager load items when fetching the session to avoid separate query inside loop
    session = db.query(StockCountSession).options(
        subqueryload(StockCountSession.items) # Load items efficiently
    ).filter(StockCountSession.id == session_id).with_for_update().first()

    if not session:
        raise ValueError(f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    if session.status != StockCountStatus.COUNTING:
        raise ValueError(f"ไม่สามารถปิดรอบนับที่สถานะ '{session.status.value}' ได้ (ต้องเป็น COUNTING)")

    items_in_session = session.items # Get items from the loaded relationship
    uncounted_items = [item for item in items_in_session if item.counted_quantity is None]
    if uncounted_items:
        product_ids_str = ", ".join(str(item.product_id) for item in uncounted_items)
        raise ValueError(
            f"กรุณาบันทึกยอดนับให้ครบทุกรายการก่อนปิดรอบนับ (สินค้า ID ที่ยังไม่ได้นับ: {product_ids_str})"
        )

    try:
        adjustments_created_count = 0
        for item in items_in_session:
            difference = item.difference # Use the @property
            if difference is not None and difference != 0:
                # Create schema for adjustment
                adjustment_data_schema = schemas.StockAdjustmentSchema(
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
                # Call record_stock_adjustment, allowing negative stock result from count
                record_stock_adjustment(db=db, adjustment_data=adjustment_data_schema, allow_negative_stock_for_count=True)
                adjustments_created_count += 1

        # Update session status and end date
        session.status = StockCountStatus.CLOSED
        session.end_date = datetime.utcnow()

        db.commit() # Commit all adjustments and session update
    except Exception as e:
        db.rollback() # Rollback ALL changes if any adjustment fails
        print(f"Error closing stock count session {session_id}: {type(e).__name__} - {e}")
        if isinstance(e, ValueError): # Re-raise specific ValueErrors (like insufficient stock if override wasn't perfect)
            raise e
        else:
            raise ValueError(f"เกิดข้อผิดพลาดในระบบขณะปิดรอบนับสต็อก: {str(e)}") from e

    db.refresh(session) # Refresh the session object after commit
    print(f"Stock Count Session {session_id} closed. {adjustments_created_count} adjustments created.")
    return session

def cancel_stock_count_session(db: Session, session_id: int) -> StockCountSession:
    """ ยกเลิกรอบนับสต็อก (ใช้ภายใน inventory_service หรือ stock_count_service) """
    session = db.query(StockCountSession).filter(StockCountSession.id == session_id).with_for_update().first()
    if not session:
        raise ValueError(f"ไม่พบรอบนับสต็อก รหัส {session_id}")
    # Allow canceling from OPEN or COUNTING status
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
        print(f"DB error canceling session {session_id}: {str(e)}")
        raise ValueError(f"DB error canceling session {session_id}") from e

    print(f"Stock Count Session {session_id} canceled.")
    return session