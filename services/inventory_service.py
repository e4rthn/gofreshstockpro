# gofresh_stockpro/services/inventory_service.py
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import func, and_, or_ 
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Dict, Any, Tuple

# Absolute Imports
from models import (Product, Location, CurrentStock, InventoryTransaction,
                    TransactionType, Category, StockCountSession,
                    StockCountItem, StockCountStatus, SaleItem)
import models
import schemas
# Import specific schemas needed
from schemas.inventory import StockInSchema, StockAdjustmentSchema, StockTransferSchema, BatchStockInSchema, StockInItemDetailSchema
from schemas.stock_count import StockCountItemUpdate # Assuming this is used by other functions if they exist here

# Absolute Imports for other services
from services import product_service, location_service # Ensure these are correctly imported

def get_current_stock_record(db: Session, product_id: int, location_id: int) -> Optional[CurrentStock]:
    """ ดึงข้อมูล CurrentStock ของสินค้าและสถานที่ที่ระบุ (พร้อม Lock สำหรับ Update) """
    return db.query(CurrentStock).filter(
        CurrentStock.product_id == product_id,
        CurrentStock.location_id == location_id
    ).with_for_update().first()

def record_stock_in(db: Session, stock_in_data: schemas.StockInSchema) -> InventoryTransaction:
    """ บันทึกการรับสินค้าเข้า, คำนวณวันหมดอายุ (ไม่ commit ที่นี่) """
    product = product_service.get_product(db, product_id=stock_in_data.product_id)
    if not product: raise ValueError(f"ไม่พบสินค้า รหัส {stock_in_data.product_id}")
    location = location_service.get_location(db, location_id=stock_in_data.location_id)
    if not location: raise ValueError(f"ไม่พบสถานที่จัดเก็บ รหัส {stock_in_data.location_id}")

    calculated_expiry_date: Optional[date] = stock_in_data.expiry_date
    if stock_in_data.production_date and product.shelf_life_days is not None and product.shelf_life_days >= 0:
        if calculated_expiry_date and stock_in_data.expiry_date != (stock_in_data.production_date + timedelta(days=int(product.shelf_life_days))):
            print(f"Warning: Expiry date provided ({stock_in_data.expiry_date}) for product {product.id} differs from calculated one. Using provided one.")
        elif not calculated_expiry_date: 
            try: calculated_expiry_date = stock_in_data.production_date + timedelta(days=int(product.shelf_life_days))
            except (TypeError, ValueError) as e: raise ValueError(f"ไม่สามารถคำนวณ Expiry Date จาก Production Date และ Shelf Life: {e}")

    elif product.shelf_life_days is not None and product.shelf_life_days >= 0 and not stock_in_data.production_date:
        if not calculated_expiry_date: 
            raise ValueError(f"สินค้า '{product.name}' มี Shelf Life กรุณาระบุ Production Date หรือ Expiry Date โดยตรง")

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
    # No commit here, should be handled by the calling route
    return transaction

def record_batch_stock_in(db: Session, batch_data: schemas.BatchStockInSchema) -> List[models.InventoryTransaction]:
    created_transactions: List[models.InventoryTransaction] = []
    
    location = location_service.get_location(db, location_id=batch_data.location_id)
    if not location:
        raise ValueError(f"ไม่พบสถานที่จัดเก็บ รหัส {batch_data.location_id}")

    if not batch_data.items:
        raise ValueError("ไม่มีรายการสินค้าใน Batch นี้")

    for item_data in batch_data.items:
        product = product_service.get_product(db, product_id=item_data.product_id)
        if not product:
            raise ValueError(f"ไม่พบสินค้า รหัส {item_data.product_id} ในรายการ Batch")

        calculated_expiry_date: Optional[date] = item_data.expiry_date
        
        if item_data.production_date and product.shelf_life_days is not None and product.shelf_life_days >= 0:
            if not calculated_expiry_date: 
                try:
                    calculated_expiry_date = item_data.production_date + timedelta(days=int(product.shelf_life_days))
                except (TypeError, ValueError) as e:
                    raise ValueError(f"สินค้า ID {product.id} ({product.sku}): ไม่สามารถคำนวณ Expiry Date. {e}")
            elif calculated_expiry_date and item_data.expiry_date != (item_data.production_date + timedelta(days=int(product.shelf_life_days))):
                 print(f"Warning (Batch Item {product.sku}): Expiry date provided ({item_data.expiry_date}) differs from calculated. Using provided one.")
        elif product.shelf_life_days is not None and product.shelf_life_days >= 0 and \
             not item_data.production_date and not item_data.expiry_date:
            raise ValueError(f"สินค้า ID {product.id} ({product.sku}): มีอายุสินค้า กรุณาระบุวันผลิต หรือวันหมดอายุโดยตรง")
        
        transaction_notes = item_data.notes # Individual item notes are None if removed from UI
        if batch_data.batch_notes and batch_data.batch_notes.strip(): 
            if transaction_notes and transaction_notes.strip(): # This will be false if item_notes is None
                transaction_notes = f"Batch: {batch_data.batch_notes}; Item: {transaction_notes}"
            else:
                transaction_notes = f"Batch: {batch_data.batch_notes}"
        
        transaction = models.InventoryTransaction(
            transaction_type=models.TransactionType.STOCK_IN,
            product_id=item_data.product_id,
            location_id=batch_data.location_id, 
            quantity_change=item_data.quantity,
            cost_per_unit=item_data.cost_per_unit, 
            production_date=item_data.production_date,
            expiry_date=calculated_expiry_date,
            notes=transaction_notes
        )
        db.add(transaction) 
        
        current_stock = get_current_stock_record(db, product_id=item_data.product_id, location_id=batch_data.location_id)
        if current_stock:
            current_stock.quantity += item_data.quantity
        else:
            current_stock = models.CurrentStock(
                product_id=item_data.product_id,
                location_id=batch_data.location_id,
                quantity=item_data.quantity
            )
            db.add(current_stock)
        
        created_transactions.append(transaction)
    # No commit here, handled by the calling route
    return created_transactions

def get_current_stock_summary(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    category_id: Optional[int] = None,
    location_id: Optional[int] = None
) -> Dict[str, Any]:
    query = db.query(CurrentStock).options(
        selectinload(CurrentStock.product).selectinload(Product.category),
        selectinload(CurrentStock.location)
    )

    # Apply filters
    if category_id is not None:
        query = query.join(CurrentStock.product).filter(Product.category_id == category_id)
    
    if location_id is not None:
        query = query.filter(CurrentStock.location_id == location_id)

    total_count = query.count()
    items_orm = []

    if total_count > 0:
        ordered_query = query 
        
        # Ensure Product is joined for ordering by Product.name.
        # If 'category_id' was not used for filtering, 'Product' might not be joined yet.
        # We can explicitly join using the relationship attribute. SQLAlchemy handles redundancy.
        if category_id is None: # Only if Product might not have been joined by the category filter
            # Check if Product is already part of the query's join entities to avoid explicit re-join if possible
            # This check can be complex. A simpler approach is to join and let SQLAlchemy optimize.
            # For clarity, if it's not filtered by category, we ensure the join for ordering.
             if not any(target.entity is Product for target in ordered_query._from_obj if hasattr(target, 'entity')): # More robust check
                ordered_query = ordered_query.join(CurrentStock.product)
             elif not isinstance(ordered_query._from_obj[0], type(CurrentStock.product.property.mapper.class_)): # Fallback
                ordered_query = ordered_query.join(CurrentStock.product)


        order_by_clauses = [Product.name]

        if location_id is None: 
            # Ensure Location is joined for ordering by Location.name
            # Similar check as for Product can be applied, or just join.
            if not any(target.entity is Location for target in ordered_query._from_obj if hasattr(target, 'entity')):
                ordered_query = ordered_query.join(CurrentStock.location)
            elif not isinstance(ordered_query._from_obj[0], type(CurrentStock.location.property.mapper.class_)): # Fallback
                 ordered_query = ordered_query.join(CurrentStock.location)

            order_by_clauses.insert(0, Location.name) 
        
        # Fallback if join checks are too complex or version-dependent:
        # ordered_query = query.join(CurrentStock.product) # Ensure Product is joined
        # order_by_clauses = [Product.name]
        # if location_id is None:
        #     ordered_query = ordered_query.join(CurrentStock.location) # Ensure Location is joined
        #     order_by_clauses.insert(0, Location.name)

        items_orm = ordered_query.order_by(*order_by_clauses).offset(skip).limit(limit).all()
    
    return {"items": items_orm, "total_count": total_count}


def get_inventory_transactions(
    db: Session,
    skip: int = 0,
    limit: int = 30,
    product_id: Optional[int] = None,
    location_id: Optional[int] = None,
    transaction_type: Optional[TransactionType] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> Dict[str, Any]:
    query = db.query(InventoryTransaction).options(
        selectinload(InventoryTransaction.product).selectinload(Product.category),
        selectinload(InventoryTransaction.location)
    )
    filters = []
    if product_id is not None:
        filters.append(InventoryTransaction.product_id == product_id)
    if location_id is not None:
        filters.append(InventoryTransaction.location_id == location_id)
    if transaction_type is not None:
        filters.append(InventoryTransaction.transaction_type == transaction_type)
    if start_date:
        start_datetime = datetime.combine(start_date, time.min)
        filters.append(InventoryTransaction.transaction_date >= start_datetime)
    if end_date:
        end_datetime = datetime.combine(end_date + timedelta(days=1), time.min)
        filters.append(InventoryTransaction.transaction_date < end_datetime)
    if filters:
        query = query.filter(and_(*filters))
    try:
        total_count = query.count()
    except Exception as count_exc:
        print(f"Error counting transactions: {count_exc}")
        total_count = 0
    transactions_data = []
    if total_count > 0 :
        transactions_data = query.order_by(
            InventoryTransaction.transaction_date.desc(),
            InventoryTransaction.id.desc()
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

    # try-except for db operations should be in the route handler to manage commit/rollback
    current_stock = get_current_stock_record(db, product_id=adjustment_data.product_id, location_id=adjustment_data.location_id)
    current_quantity_on_hand = current_stock.quantity if current_stock else 0.0 
    if adjustment_data.quantity_change < 0:
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
    )
    db.add(transaction)
    if current_stock:
        current_stock.quantity += adjustment_data.quantity_change
    else:
        if adjustment_data.quantity_change > 0 or allow_negative_stock_for_count:
            current_stock = CurrentStock(
                product_id=adjustment_data.product_id,
                location_id=adjustment_data.location_id,
                quantity=adjustment_data.quantity_change
            )
            db.add(current_stock)
        else:
             raise ValueError("ไม่สามารถปรับปรุงยอดติดลบสำหรับสต็อกที่ยังไม่มีได้ (ยกเว้นกรณีมาจากการนับสต็อก)")
    # No commit here
    return transaction


def record_stock_deduction(
    db: Session,
    transaction_type: TransactionType,
    product_id: int,
    location_id: int,
    quantity: float, 
    related_transaction_id: Optional[int] = None,
    notes: Optional[str] = None,
    cost_per_unit: Optional[float] = None 
) -> InventoryTransaction:
    if quantity <= 0:
        raise ValueError("Quantity for stock deduction must be a positive value.")

    # Ensure the product and location exist (can be omitted if guaranteed by caller)
    # product = product_service.get_product(db, product_id=product_id)
    # if not product: raise ValueError(f"ไม่พบสินค้า รหัส {product_id} สำหรับการตัดสต็อก")
    # location = location_service.get_location(db, location_id=location_id)
    # if not location: raise ValueError(f"ไม่พบสถานที่จัดเก็บ รหัส {location_id} สำหรับการตัดสต็อก")

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
        print(f"Warning: Deducting stock for non-existent record (Product ID: {product_id}, Location ID: {location_id}). Creating new negative stock record.")
        current_stock_record = CurrentStock(
            product_id=product_id,
            location_id=location_id,
            quantity = -abs(quantity) 
        )
        db.add(current_stock_record)
    # No commit here
    return transaction


def get_near_expiry_transactions(
    db: Session, days_ahead: int = 30, skip: int = 0, limit: int = 100
) -> Dict[str, Any]:
    today = date.today()
    expiry_threshold_date = today + timedelta(days=days_ahead)
    query = db.query(InventoryTransaction).options(
        selectinload(InventoryTransaction.product).selectinload(Product.category), 
        selectinload(InventoryTransaction.location)
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
    
    from_stock = get_current_stock_record(db, product_id=transfer_data.product_id, location_id=transfer_data.from_location_id)
    from_quantity_on_hand = from_stock.quantity if from_stock else 0.0
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
        transaction_type=TransactionType.TRANSFER_OUT,
        product_id=transfer_data.product_id,
        location_id=transfer_data.from_location_id,
        quantity_change= -abs(transfer_data.quantity),
        notes=notes_out_detail,
        cost_per_unit=cost_for_transfer_tx 
    )
    db.add(tx_out)
    db.flush() 

    tx_in = InventoryTransaction(
        transaction_type=TransactionType.TRANSFER_IN,
        product_id=transfer_data.product_id,
        location_id=transfer_data.to_location_id,
        quantity_change= abs(transfer_data.quantity),
        notes=notes_in_detail,
        cost_per_unit=cost_for_transfer_tx,
        related_transaction_id=tx_out.id 
    )
    db.add(tx_in)
    if from_stock: 
        from_stock.quantity -= abs(transfer_data.quantity)
    
    to_stock = get_current_stock_record(db, product_id=transfer_data.product_id, location_id=transfer_data.to_location_id)
    if to_stock:
        to_stock.quantity += abs(transfer_data.quantity)
    else:
        to_stock = CurrentStock(
            product_id=transfer_data.product_id,
            location_id=transfer_data.to_location_id,
            quantity=abs(transfer_data.quantity)
        )
        db.add(to_stock)
    # No commit here
    return tx_out, tx_in