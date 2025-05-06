# services/product_service.py
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any

# Absolute Imports
from models import Product, Category # Import models ที่ Service นี้ใช้งานโดยตรง
import schemas # Import schemas package
from services import category_service # Import service อื่นที่เรียกใช้

def get_product(db: Session, product_id: int) -> Optional[Product]:
    """ ดึงข้อมูล Product ตาม ID พร้อม Category (Eager Loading) """
    return db.query(Product).options(joinedload(Product.category)).filter(Product.id == product_id).first()

def get_product_by_sku(db: Session, sku: str) -> Optional[Product]:
    """ ดึงข้อมูล Product ตาม SKU พร้อม Category (Eager Loading) """
    return db.query(Product).options(joinedload(Product.category)).filter(Product.sku == sku).first()

def get_products(db: Session, skip: int = 0, limit: int = 100) -> Dict[str, Any]:
    """ ดึงข้อมูล Product หลายรายการ พร้อม Category และ Pagination Info """
    query = db.query(Product).options(joinedload(Product.category))
    total_count = query.count()
    products_data = query.order_by(Product.id).offset(skip).limit(limit).all()
    return {"items": products_data, "total_count": total_count}

def get_products_by_category(db: Session, category_id: int, skip: int = 0, limit: int = 100) -> Dict[str, Any]:
    """ ดึงข้อมูล Product ตาม Category ID พร้อม Pagination Info """
    category = category_service.get_category(db, category_id=category_id)
    if not category: raise ValueError(f"ไม่พบหมวดหมู่รหัส {category_id}")
    query = db.query(Product).options(joinedload(Product.category)).filter(Product.category_id == category_id)
    total_count = query.count()
    products_data = query.order_by(Product.id).offset(skip).limit(limit).all()
    return {"items": products_data, "total_count": total_count}

def create_product(db: Session, product: schemas.ProductCreate) -> Product:
    """ สร้าง Product ใหม่ """
    category = category_service.get_category(db, category_id=product.category_id)
    if not category: raise ValueError(f"ไม่พบหมวดหมู่รหัส {product.category_id} ไม่สามารถสร้างสินค้าได้")
    existing_product = get_product_by_sku(db, sku=product.sku)
    if existing_product: raise ValueError(f"มีสินค้า SKU '{product.sku}' อยู่ในระบบแล้ว")
    db_product = Product(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    created_product = get_product(db, product_id=db_product.id)
    if created_product is None: raise RuntimeError(f"Failed to fetch newly created product with id {db_product.id}")
    return created_product

def update_product(db: Session, product_id: int, product_update: schemas.ProductCreate) -> Optional[Product]:
    """ อัปเดตข้อมูล Product """
    db_product = db.query(Product).filter(Product.id == product_id).with_for_update().first()
    if not db_product: return None
    if product_update.category_id != db_product.category_id:
        category = category_service.get_category(db, category_id=product_update.category_id)
        if not category: raise ValueError(f"ไม่พบหมวดหมู่รหัส {product_update.category_id}")
    if product_update.sku != db_product.sku:
         existing_product = get_product_by_sku(db, sku=product_update.sku)
         if existing_product and existing_product.id != product_id: raise ValueError(f"มีสินค้า SKU '{product_update.sku}' อยู่ในระบบแล้ว")
    update_data = product_update.model_dump()
    for key, value in update_data.items(): setattr(db_product, key, value)
    db.commit()
    updated_product = get_product(db, product_id=db_product.id)
    if updated_product is None: raise RuntimeError(f"Failed to fetch updated product with id {db_product.id}")
    return updated_product

def delete_product(db: Session, product_id: int) -> Optional[schemas.Product]: # คืนค่า Schema
    """ ลบ Product และคืนค่าข้อมูลที่ถูกลบในรูปแบบ Schema """
    db_product = db.query(Product).options(joinedload(Product.category)).filter(Product.id == product_id).first()
    if not db_product: return None
    # TODO: เพิ่มการตรวจสอบ Dependency กับ InventoryTransaction, CurrentStock, SaleItem, StockCountItem ก่อนลบ
    deleted_product_data = schemas.Product.model_validate(db_product)
    db.delete(db_product)
    db.commit()
    return deleted_product_data

def get_products_basic_by_category(db: Session, category_id: int) -> List[schemas.ProductBasic]: # คืน List ของ Schema
    """ ดึงข้อมูล Product แบบย่อ (id, name, sku, price_b2c, standard_cost) ตาม Category ID """
    results = db.query(
        Product.id, Product.name, Product.sku, Product.price_b2c, Product.standard_cost
    ).filter(Product.category_id == category_id).order_by(Product.name).all()
    products_basic_list = [
        schemas.ProductBasic(id=row.id, name=row.name, sku=row.sku, price_b2c=row.price_b2c, standard_cost=row.standard_cost)
        for row in results
    ]
    return products_basic_list