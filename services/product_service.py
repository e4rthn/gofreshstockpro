# services/product_service.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from typing import List, Optional, Dict, Any
import datetime

# Import models and schemas directly
from models.product import Product
from models.category import Category # If used directly for type hinting or checks
import schemas # To access schemas like schemas.ProductCreate, schemas.ProductUpdate, etc.
from services import category_service # For dependency
import models # For other models like CurrentStock, InventoryTransaction etc. in delete_product

# --- Core Product Retrieval Functions ---

def get_product(db: Session, product_id: int) -> Optional[Product]:
    """ ดึงข้อมูล Product พร้อม Category """
    return db.query(Product).options(joinedload(Product.category)).filter(Product.id == product_id).first()

def get_product_by_sku(db: Session, sku: str) -> Optional[Product]:
    """ ดึงข้อมูล Product ตาม SKU พร้อม Category """
    return db.query(Product).options(joinedload(Product.category)).filter(Product.sku == sku).first()

def get_product_by_barcode(db: Session, barcode: str) -> Optional[Product]:
    """ ดึงข้อมูล Product ตาม Barcode พร้อม Category """
    if not barcode: return None # Handle empty barcode string if necessary
    return db.query(Product).options(joinedload(Product.category)).filter(Product.barcode == barcode).first()

def get_product_by_scan_code(db: Session, scan_code: str) -> Optional[Product]:
    """ ดึงข้อมูล Product ตาม Barcode หรือ SKU พร้อม Category """
    if not scan_code: return None
    # Prioritize barcode, then SKU, or use OR condition
    product = db.query(Product).options(joinedload(Product.category)).filter(
        or_(Product.barcode == scan_code, Product.sku == scan_code)
    ).order_by(
        Product.barcode.isnot(None).desc(), # Prefer items with barcode if scan_code matches barcode
        Product.id # Fallback ordering
    ).first()
    return product

# --- Listing and Grouping Functions ---

def get_products(db: Session, skip: int = 0, limit: int = 100) -> Dict[str, Any]:
    """ ดึงรายการ Product ทั้งหมด พร้อม Category และ Pagination Info """
    query = db.query(Product).options(joinedload(Product.category))
    total_count = query.count()
    products_data = query.order_by(Product.id).offset(skip).limit(limit).all()
    return {"items": products_data, "total_count": total_count}

def get_products_by_category(db: Session, category_id: int, skip: int = 0, limit: int = 100) -> Dict[str, Any]:
    """ ดึงรายการ Product ตาม Category พร้อม Pagination Info """
    category = category_service.get_category(db, category_id=category_id)
    if not category:
        return {"items": [], "total_count": 0}
    query = db.query(Product).options(joinedload(Product.category)).filter(Product.category_id == category_id)
    total_count = query.count()
    products_data = query.order_by(Product.name).offset(skip).limit(limit).all()
    return {"items": products_data, "total_count": total_count}

def get_products_basic_by_category(db: Session, category_id: int) -> List[schemas.ProductBasic]:
    """ ดึงข้อมูล Product แบบย่อ (สำหรับ Dropdown) ตาม Category """
    db_category = db.query(Category).filter(Category.id == category_id).first()
    if not db_category:
        print(f"Category ID {category_id} not found in service.")
        return []

    results = db.query(
        Product.id, Product.name, Product.sku, Product.price_b2c, Product.price_b2b,
        Product.standard_cost, Product.barcode, Product.shelf_life_days
    ).filter(Product.category_id == category_id).order_by(Product.name).all()

    if not results:
        print(f"No products found for category ID {category_id}.")
    # else:
    #      print(f"Found {len(results)} products for category ID {category_id}.") # Optional: for debugging

    return [
        schemas.ProductBasic.model_validate(row._asdict()) for row in results
    ]

# --- Create, Update, Delete Functions ---

def create_product(db: Session, product_in: schemas.ProductCreate) -> Product:
    """ สร้าง Product ใหม่ """
    category = category_service.get_category(db, category_id=product_in.category_id)
    if not category:
        raise ValueError(f"ไม่พบหมวดหมู่รหัส {product_in.category_id}")

    if get_product_by_sku(db, sku=product_in.sku):
        raise ValueError(f"มีสินค้า SKU '{product_in.sku}' อยู่ในระบบแล้ว")

    if product_in.barcode and get_product_by_barcode(db, barcode=product_in.barcode):
        raise ValueError(f"มีสินค้า Barcode '{product_in.barcode}' อยู่ในระบบแล้ว")

    db_product_data = product_in.model_dump(
        exclude={'previous_price_b2c', 'price_b2c_last_changed', 'previous_price_b2b', 'price_b2b_last_changed'},
        exclude_unset=True # Only include fields that were explicitly set by the client
    )
    db_product = Product(**db_product_data)
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return get_product(db, product_id=db_product.id) # Return with category loaded


def update_product(db: Session, product_id: int, product_update: schemas.ProductUpdate) -> Optional[Product]:
    """ อัปเดตข้อมูล Product (เก็บ previous_price_b2c และ previous_price_b2b) """
    db_product = get_product(db, product_id=product_id)
    if not db_product:
        return None

    update_data = product_update.model_dump(exclude_unset=True)
    utc_now = datetime.datetime.now(datetime.timezone.utc)

    # Track B2C price changes
    if 'price_b2c' in update_data and update_data['price_b2c'] is not None:
        new_price_b2c = float(update_data['price_b2c'])
        current_db_price_b2c = float(db_product.price_b2c) if db_product.price_b2c is not None else None
        if current_db_price_b2c is None or abs(new_price_b2c - current_db_price_b2c) > 1e-9: # Epsilon for float comparison
            if current_db_price_b2c is not None:
                db_product.previous_price_b2c = current_db_price_b2c
            db_product.price_b2c_last_changed = utc_now

    # Track B2B price changes
    if 'price_b2b' in update_data: # price_b2b can be set to None
        new_price_b2b = float(update_data['price_b2b']) if update_data['price_b2b'] is not None else None
        current_db_price_b2b = float(db_product.price_b2b) if db_product.price_b2b is not None else None
        
        price_actually_changed = False
        if new_price_b2b is None and current_db_price_b2b is not None: # Changed to None
            price_actually_changed = True
        elif new_price_b2b is not None and current_db_price_b2b is None: # Changed from None to a value
            price_actually_changed = True
        elif new_price_b2b is not None and current_db_price_b2b is not None and abs(new_price_b2b - current_db_price_b2b) > 1e-9: # Value changed
            price_actually_changed = True
            
        if price_actually_changed:
            if current_db_price_b2b is not None: # Only store previous if it existed
                db_product.previous_price_b2b = current_db_price_b2b
            db_product.price_b2b_last_changed = utc_now

    # Validate category, SKU, Barcode (if changed)
    if 'category_id' in update_data and update_data['category_id'] != db_product.category_id:
        category = category_service.get_category(db, category_id=update_data['category_id'])
        if not category:
            raise ValueError(f"ไม่พบหมวดหมู่รหัส {update_data['category_id']}")

    if 'sku' in update_data and update_data['sku'] != db_product.sku:
        existing_sku = get_product_by_sku(db, sku=update_data['sku'])
        if existing_sku and existing_sku.id != product_id:
            raise ValueError(f"มีสินค้า SKU '{update_data['sku']}' อยู่ในระบบแล้ว ({existing_sku.name})")

    if 'barcode' in update_data and update_data['barcode'] != db_product.barcode:
        if update_data['barcode'] is not None: # Only check for duplicates if new barcode is not None
            existing_barcode = get_product_by_barcode(db, barcode=update_data['barcode'])
            if existing_barcode and existing_barcode.id != product_id:
                raise ValueError(f"มีสินค้า Barcode '{update_data['barcode']}' อยู่ในระบบแล้ว ({existing_barcode.name})")

    # Update product attributes
    for key, value in update_data.items():
        setattr(db_product, key, value)

    db.commit()
    db.refresh(db_product)
    # Eager load category again after refresh for the returned object
    return get_product(db, product_id=db_product.id)


def delete_product(db: Session, product_id: int) -> Optional[schemas.Product]:
    """ ลบ Product (พร้อมตรวจสอบ Dependency อย่างละเอียด) """
    db_product = get_product(db, product_id=product_id) # This already loads the category
    if not db_product:
        return None # Product not found, nothing to delete

    # 1. Check CurrentStock - Allow deletion if stock record exists but quantity is zero
    current_stock_record = db.query(models.CurrentStock).filter(
        models.CurrentStock.product_id == product_id
    ).first()

    # Determine if quantity is effectively zero (handles both int and float cases)
    is_stock_effectively_zero = True
    if current_stock_record:
        if isinstance(current_stock_record.quantity, float):
            is_stock_effectively_zero = abs(current_stock_record.quantity) < 1e-9 # Epsilon for float
        else: # Assuming Integer
            is_stock_effectively_zero = current_stock_record.quantity == 0

    if current_stock_record and not is_stock_effectively_zero:
        raise ValueError(f"ไม่สามารถลบสินค้า '{db_product.name}' ได้ เนื่องจากยังมีสต็อกคงเหลืออยู่ (จำนวน: {current_stock_record.quantity})")

    # 2. Check InventoryTransaction
    if db.query(models.InventoryTransaction).filter(models.InventoryTransaction.product_id == product_id).first():
        raise ValueError(f"ไม่สามารถลบสินค้า '{db_product.name}' ได้ เนื่องจากมีประวัติ Transaction เกี่ยวข้อง")

    # 3. Check SaleItem
    if db.query(models.SaleItem).filter(models.SaleItem.product_id == product_id).first():
         raise ValueError(f"ไม่สามารถลบสินค้า '{db_product.name}' ได้ เนื่องจากมีประวัติการขายเกี่ยวข้อง")

    # 4. Check StockCountItem
    if db.query(models.StockCountItem).filter(models.StockCountItem.product_id == product_id).first():
         raise ValueError(f"ไม่สามารถลบสินค้า '{db_product.name}' ได้ เนื่องจากมีประวัติการตรวจนับสต็อกเกี่ยวข้อง")

    # If all checks pass, proceed with deletion
    # If there's a CurrentStock record with zero quantity, delete it as well for cleanliness.
    if current_stock_record and is_stock_effectively_zero:
        print(f"Deleting zero quantity CurrentStock record (ID: {current_stock_record.id}) for product ID {product_id} before deleting product.")
        db.delete(current_stock_record)
        # The commit will happen after deleting the product itself.

    # Convert to schema before deletion to retain data for response
    deleted_product_schema = schemas.Product.model_validate(db_product)

    db.delete(db_product)
    db.commit() # Commit all deletions (product and zero-stock CurrentStock)
    
    return deleted_product_schema