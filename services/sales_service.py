# services/sales_service.py
from sqlalchemy.orm import Session, joinedload, subqueryload
from typing import List, Optional, Dict, Any
from datetime import date, datetime, time, timedelta

# Absolute Imports
import models
import schemas
from services import inventory_service, product_service, location_service

def record_sale(db: Session, sale_data: schemas.SaleCreate, allow_negative_stock_on_sale: bool = False) -> models.Sale:
    """
    บันทึกการขายใหม่ และจัดการ Transaction และ Stock.
    :param allow_negative_stock_on_sale: ถ้าเป็น True, จะอนุญาตให้ขายได้แม้สต็อกในระบบจะติดลบหรือเป็นศูนย์
                                          (ใช้สำหรับกรณีที่ยืนยันว่ามีของหน้าร้านจริง)
    """
    try:
        location = location_service.get_location(db, location_id=sale_data.location_id)
        if not location:
            raise ValueError(f"ไม่พบสถานที่จัดเก็บ รหัส {sale_data.location_id}")
        if not sale_data.items:
            raise ValueError("ไม่สามารถบันทึกการขายที่ไม่มีรายการสินค้าได้")

        total_sale_amount = 0.0
        items_to_process = []

        for item_data in sale_data.items:
            product = product_service.get_product(db, product_id=item_data.product_id)
            if not product:
                raise ValueError(f"ไม่พบสินค้า รหัส {item_data.product_id}")

            current_stock_record = inventory_service.get_current_stock_record(
                db, product_id=item_data.product_id, location_id=sale_data.location_id
            )
            current_quantity_in_system = current_stock_record.quantity if current_stock_record else 0

            if not allow_negative_stock_on_sale:
                if current_quantity_in_system < item_data.quantity:
                    raise ValueError(
                        f"สต็อกในระบบไม่เพียงพอสำหรับสินค้า '{product.name}' (SKU: {product.sku}) ที่ {location.name}. "
                        f"ต้องการ: {item_data.quantity}, ในระบบมี: {current_quantity_in_system}"
                    )

            item_total = item_data.quantity * item_data.unit_price
            total_sale_amount += item_total
            items_to_process.append({
                "data": item_data,
                "product": product,
                "current_system_stock_before_sale": current_quantity_in_system
            })

        db_sale = models.Sale(
            location_id=sale_data.location_id,
            total_amount=total_sale_amount,
            notes=sale_data.notes,
            # sale_date จะถูกตั้งค่า default โดย database (server_default=func.now())
        )
        db.add(db_sale)
        db.flush() # Ensure db_sale.id is available

        for item_info in items_to_process:
            item_data_schema = item_info["data"]
            # Ensure all fields required by SaleItem model are present
            # Pydantic's model_dump will convert the schema to a dict
            sale_item_dict_for_model = item_data_schema.model_dump()

            db_sale_item = models.SaleItem(sale_id=db_sale.id, **sale_item_dict_for_model)
            db.add(db_sale_item)

            inventory_service.record_stock_deduction(
                db=db,
                transaction_type=models.TransactionType.SALE,
                product_id=item_data_schema.product_id,
                location_id=sale_data.location_id,
                quantity=item_data_schema.quantity,
                related_transaction_id=db_sale.id,
                notes=f"Sale #{db_sale.id}. System stock before: {item_info['current_system_stock_before_sale']}",
                # cost_per_unit for sale deduction is usually not the sale price, but the product's standard_cost.
                # This might need to be fetched and passed if you want to log cost with sale transactions.
                # For now, it's not explicitly passed to record_stock_deduction's InventoryTransaction.
            )
        db.commit()

    except Exception as e:
        db.rollback()
        print(f"Error in record_sale: {type(e).__name__} - {e}") # Log the type of error as well
        if isinstance(e, ValueError): # Re-raise known ValueErrors
            raise e
        else: # Wrap other exceptions
            raise ValueError(f"เกิดข้อผิดพลาดในระบบขณะบันทึกการขาย (โปรดตรวจสอบ log): {type(e).__name__}") from e

    final_sale = db.query(models.Sale).options(
        subqueryload(models.Sale.items).joinedload(models.SaleItem.product).joinedload(models.Product.category),
        joinedload(models.Sale.location)
    ).filter(models.Sale.id == db_sale.id).first()

    if final_sale is None:
        raise RuntimeError("Critical error: Failed to fetch newly created sale after commit.")
    return final_sale

def get_sales_report(
    db: Session, start_date: Optional[date] = None, end_date: Optional[date] = None,
    skip: int = 0, limit: int = 100
) -> Dict[str, Any]:
    query = db.query(models.Sale).options(
        joinedload(models.Sale.location),
        subqueryload(models.Sale.items).joinedload(models.SaleItem.product).joinedload(models.Product.category)
    )
    if start_date:
        start_datetime = datetime.combine(start_date, time.min)
        query = query.filter(models.Sale.sale_date >= start_datetime)
    if end_date:
        # To include the entire end_date, filter up to the beginning of the next day
        end_datetime = datetime.combine(end_date + timedelta(days=1), time.min)
        query = query.filter(models.Sale.sale_date < end_datetime)

    total_count = query.count()
    sales_data = query.order_by(models.Sale.sale_date.desc()).offset(skip).limit(limit).all()
    return {"sales": sales_data, "total_count": total_count}