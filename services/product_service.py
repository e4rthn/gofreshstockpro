# services/product_service.py
from sqlalchemy.orm import Session, joinedload, exc
from sqlalchemy import or_
from typing import List, Optional, Dict, Any

# Import models and schemas directly
from models.product import Product
from models.category import Category # If used directly
import schemas # To access schemas like schemas.ProductCreate, schemas.ProductUpdate, etc.
from services import category_service # For dependency
import models

# --- Core Product Retrieval Functions ---

def get_product(db: Session, product_id: int) -> Optional[Product]:
    """ ดึงข้อมูล Product พร้อม Category """
    return db.query(Product).options(joinedload(Product.category)).filter(Product.id == product_id).first()

def get_product_by_sku(db: Session, sku: str) -> Optional[Product]:
    """ ดึงข้อมูล Product ตาม SKU พร้อม Category """
    return db.query(Product).options(joinedload(Product.category)).filter(Product.sku == sku).first()

def get_product_by_barcode(db: Session, barcode: str) -> Optional[Product]:
    """ ดึงข้อมูล Product ตาม Barcode พร้อม Category """
    if not barcode: return None
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
        # Consider returning empty dict or raising specific error
        # For now, returning empty dict to avoid breaking UI list if category deleted
        return {"items": [], "total_count": 0}
        # raise ValueError(f"ไม่พบหมวดหมู่รหัส {category_id}")
    query = db.query(Product).options(joinedload(Product.category)).filter(Product.category_id == category_id)
    total_count = query.count()
    products_data = query.order_by(Product.name).offset(skip).limit(limit).all()
    return {"items": products_data, "total_count": total_count}

# *** แก้ไข get_products_basic_by_category ให้ดึง shelf_life_days ***
def get_products_basic_by_category(db: Session, category_id: int) -> List[schemas.ProductBasic]:
    """ ดึงข้อมูล Product แบบย่อ (สำหรับ Dropdown) ตาม Category """
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        # Return empty list if category not found, API will return []
        print(f"Category ID {category_id} not found in service.") # Add print for debugging
        return []

    # --- เพิ่ม shelf_life_days เข้าไปใน Query ---
    results = db.query(
        Product.id, Product.name, Product.sku, Product.price_b2c,
        Product.standard_cost, Product.barcode, Product.shelf_life_days # <--- เพิ่มตรงนี้
    ).filter(Product.category_id == category_id).order_by(Product.name).all()
    # ----------------------------------------

    if not results:
        print(f"No products found for category ID {category_id}.") # Add print for debugging
    else:
         print(f"Found {len(results)} products for category ID {category_id}.")

    # Use model_validate for Pydantic v2
    # ProductBasic schema ต้องมี field shelf_life_days รองรับแล้ว
    return [
        schemas.ProductBasic.model_validate(row._asdict()) for row in results
    ]
# *** สิ้นสุดการแก้ไข ***


# --- Create, Update, Delete Functions ---

def create_product(db: Session, product_in: schemas.ProductCreate) -> Product:
    """ สร้าง Product ใหม่ (รองรับ shelf_life_days) """
    category = category_service.get_category(db, category_id=product_in.category_id)
    if not category:
        raise ValueError(f"ไม่พบหมวดหมู่รหัส {product_in.category_id}")

    existing_sku = get_product_by_sku(db, sku=product_in.sku)
    if existing_sku:
        raise ValueError(f"มีสินค้า SKU '{product_in.sku}' อยู่ในระบบแล้ว ({existing_sku.name})")

    if product_in.barcode: # Check if barcode is provided and not empty
        existing_barcode = get_product_by_barcode(db, barcode=product_in.barcode)
        if existing_barcode:
            raise ValueError(f"มีสินค้า Barcode '{product_in.barcode}' อยู่ในระบบแล้ว ({existing_barcode.name})")

    # shelf_life_days is included in product_in if provided
    db_product = Product(**product_in.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    # Return with category loaded for consistency
    return get_product(db, product_id=db_product.id)

def update_product(db: Session, product_id: int, product_update: schemas.ProductUpdate) -> Optional[Product]:
    """ อัปเดตข้อมูล Product (รองรับ shelf_life_days) """
    db_product = get_product(db, product_id=product_id)
    if not db_product:
        return None # Product not found

    # Get update data, excluding fields not set in the request
    update_data = product_update.model_dump(exclude_unset=True)

    # Validate category if it's being changed
    if 'category_id' in update_data and update_data['category_id'] != db_product.category_id:
        category = category_service.get_category(db, category_id=update_data['category_id'])
        if not category:
            raise ValueError(f"ไม่พบหมวดหมู่รหัส {update_data['category_id']}")

    # Validate SKU uniqueness if it's being changed
    if 'sku' in update_data and update_data['sku'] != db_product.sku:
        existing_sku = get_product_by_sku(db, sku=update_data['sku'])
        if existing_sku and existing_sku.id != product_id:
            raise ValueError(f"มีสินค้า SKU '{update_data['sku']}' อยู่ในระบบแล้ว ({existing_sku.name})")

    # Validate Barcode uniqueness if it's being changed
    # Handle case where barcode is set to None or empty string (meaning clear barcode)
    if 'barcode' in update_data:
        new_barcode = update_data['barcode'] # Already validated by Pydantic (None or str)
        if new_barcode != db_product.barcode: # Check only if it's actually changing
            if new_barcode is not None: # Only check for duplicates if the new barcode is not None
                existing_barcode = get_product_by_barcode(db, barcode=new_barcode)
                if existing_barcode and existing_barcode.id != product_id:
                    raise ValueError(f"มีสินค้า Barcode '{new_barcode}' อยู่ในระบบแล้ว ({existing_barcode.name})")
            # If new_barcode is None, allow setting it (clearing the barcode)
    # shelf_life_days validation (e.g., non-negative) is handled by Pydantic

    # Update the product attributes
    for key, value in update_data.items():
        setattr(db_product, key, value)

    db.commit()
    db.refresh(db_product)
    # Eager load category again after refresh for the returned object
    updated_product_with_category = get_product(db, product_id=db_product.id)
    return updated_product_with_category


def delete_product(db: Session, product_id: int) -> Optional[schemas.Product]:
    """ ลบ Product (ควรเพิ่มการตรวจสอบ Dependency) """
    # Needs careful dependency check before actual deletion
    db_product = get_product(db, product_id=product_id)
    if not db_product:
        return None

    # --- Add Dependency Checks ---
    # Check CurrentStock
    if db.query(models.CurrentStock).filter(models.CurrentStock.product_id == product_id).first():
        raise ValueError(f"ไม่สามารถลบสินค้า '{db_product.name}' ได้ เนื่องจากมีข้อมูลสต็อกคงเหลืออยู่")
    # Check InventoryTransaction
    if db.query(models.InventoryTransaction).filter(models.InventoryTransaction.product_id == product_id).first():
        raise ValueError(f"ไม่สามารถลบสินค้า '{db_product.name}' ได้ เนื่องจากมีประวัติ Transaction เกี่ยวข้อง")
    # Check SaleItem
    if db.query(models.SaleItem).filter(models.SaleItem.product_id == product_id).first():
         raise ValueError(f"ไม่สามารถลบสินค้า '{db_product.name}' ได้ เนื่องจากมีประวัติการขายเกี่ยวข้อง")
    # Check StockCountItem
    if db.query(models.StockCountItem).filter(models.StockCountItem.product_id == product_id).first():
         raise ValueError(f"ไม่สามารถลบสินค้า '{db_product.name}' ได้ เนื่องจากมีประวัติการตรวจนับสต็อกเกี่ยวข้อง")
    # --------------------------

    # If checks pass, proceed with deletion
    deleted_product_schema = schemas.Product.model_validate(db_product) # Pydantic V2
    db.delete(db_product)
    db.commit()
    return deleted_product_schema