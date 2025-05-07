# services/product_service.py
from sqlalchemy.orm import Session, joinedload, exc
from sqlalchemy import or_
from typing import List, Optional, Dict, Any

# Import models and schemas directly
from models.product import Product
from models.category import Category # If used directly
import schemas # To access schemas like schemas.ProductCreate, schemas.ProductUpdate, etc.
from services import category_service # For dependency

# --- Core Product Retrieval Functions ---

def get_product(db: Session, product_id: int) -> Optional[Product]:
    return db.query(Product).options(joinedload(Product.category)).filter(Product.id == product_id).first()

def get_product_by_sku(db: Session, sku: str) -> Optional[Product]:
    return db.query(Product).options(joinedload(Product.category)).filter(Product.sku == sku).first()

def get_product_by_barcode(db: Session, barcode: str) -> Optional[Product]:
    if not barcode: return None
    return db.query(Product).options(joinedload(Product.category)).filter(Product.barcode == barcode).first()

def get_product_by_scan_code(db: Session, scan_code: str) -> Optional[Product]:
    if not scan_code: return None
    # Prioritize barcode, then SKU, or use OR condition
    product = db.query(Product).options(joinedload(Product.category)).filter(
        or_(Product.barcode == scan_code, Product.sku == scan_code)
    ).order_by(
        # Optional: prioritize exact match on barcode if possible, or by ID
        # This might need more complex ordering if a code could be both a SKU and a barcode for different items
        Product.barcode.isnot(None).desc(), # Prefer items with barcode if scan_code matches barcode
        Product.id # Fallback ordering
    ).first()
    return product

# --- Listing and Grouping Functions ---

def get_products(db: Session, skip: int = 0, limit: int = 100) -> Dict[str, Any]:
    query = db.query(Product).options(joinedload(Product.category))
    total_count = query.count()
    products_data = query.order_by(Product.id).offset(skip).limit(limit).all()
    return {"items": products_data, "total_count": total_count}

def get_products_by_category(db: Session, category_id: int, skip: int = 0, limit: int = 100) -> Dict[str, Any]:
    category = category_service.get_category(db, category_id=category_id)
    if not category:
        raise ValueError(f"ไม่พบหมวดหมู่รหัส {category_id}")
    query = db.query(Product).options(joinedload(Product.category)).filter(Product.category_id == category_id)
    total_count = query.count()
    products_data = query.order_by(Product.name).offset(skip).limit(limit).all()
    return {"items": products_data, "total_count": total_count}

def get_products_basic_by_category(db: Session, category_id: int) -> List[schemas.ProductBasic]:
    # Check if category exists first
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        # Return empty list if category not found
        print(f"Category ID {category_id} not found in service.") # Add print for debugging
        return []

    results = db.query(
        Product.id, Product.name, Product.sku, Product.price_b2c, Product.standard_cost, Product.barcode
    ).filter(Product.category_id == category_id).order_by(Product.name).all()

    if not results:
        print(f"No products found for category ID {category_id}.") # Add print for debugging
    else:
         print(f"Found {len(results)} products for category ID {category_id}.")

    # Use model_validate for Pydantic v2
    return [
        schemas.ProductBasic.model_validate(row._asdict()) for row in results
    ]

# --- Create, Update, Delete Functions ---

def create_product(db: Session, product_in: schemas.ProductCreate) -> Product:
    category = category_service.get_category(db, category_id=product_in.category_id)
    if not category:
        raise ValueError(f"ไม่พบหมวดหมู่รหัส {product_in.category_id}")

    existing_sku = get_product_by_sku(db, sku=product_in.sku)
    if existing_sku:
        raise ValueError(f"มีสินค้า SKU '{product_in.sku}' อยู่ในระบบแล้ว ({existing_sku.name})")

    if product_in.barcode:
        existing_barcode = get_product_by_barcode(db, barcode=product_in.barcode)
        if existing_barcode:
            raise ValueError(f"มีสินค้า Barcode '{product_in.barcode}' อยู่ในระบบแล้ว ({existing_barcode.name})")

    db_product = Product(**product_in.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return get_product(db, product_id=db_product.id) # Return with category loaded

def update_product(db: Session, product_id: int, product_update: schemas.ProductUpdate) -> Optional[Product]:
    db_product = get_product(db, product_id=product_id)
    if not db_product:
        return None

    update_data = product_update.model_dump(exclude_unset=True)

    if 'category_id' in update_data and update_data['category_id'] != db_product.category_id:
        category = category_service.get_category(db, category_id=update_data['category_id'])
        if not category:
            raise ValueError(f"ไม่พบหมวดหมู่รหัส {update_data['category_id']}")
    
    if 'sku' in update_data and update_data['sku'] != db_product.sku:
        existing_sku = get_product_by_sku(db, sku=update_data['sku'])
        if existing_sku and existing_sku.id != product_id:
            raise ValueError(f"มีสินค้า SKU '{update_data['sku']}' อยู่ในระบบแล้ว ({existing_sku.name})")

    if 'barcode' in update_data: # Check if barcode is part of the update
        new_barcode = update_data.get('barcode') # Use .get() for safety
        if new_barcode == "": new_barcode = None # Treat empty string as None

        if new_barcode != db_product.barcode: # Only check for duplicates if it's a new, non-null barcode
            if new_barcode is not None:
                existing_barcode = get_product_by_barcode(db, barcode=new_barcode)
                if existing_barcode and existing_barcode.id != product_id:
                    raise ValueError(f"มีสินค้า Barcode '{new_barcode}' อยู่ในระบบแล้ว ({existing_barcode.name})")
    
    for key, value in update_data.items():
        setattr(db_product, key, value)
            
    db.commit()
    db.refresh(db_product)
    return get_product(db, product_id=db_product.id) # Return with category loaded

def delete_product(db: Session, product_id: int) -> Optional[schemas.Product]:
    db_product = get_product(db, product_id=product_id)
    if not db_product:
        return None
    # TODO: Add proper dependency checks (CurrentStock, InventoryTransaction, etc.)
    # For example:
    # if db.query(models.CurrentStock).filter(models.CurrentStock.product_id == product_id).first():
    #     raise ValueError(f"Cannot delete product '{db_product.name}' as it has stock records.")

    deleted_product_schema = schemas.Product.model_validate(db_product)
    db.delete(db_product)
    db.commit()
    return deleted_product_schema