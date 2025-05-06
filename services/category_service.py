# services/category_service.py
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

# Absolute Imports
from models import Category, Product
import schemas # Using 'import schemas' then 'schemas.CategoryCreate'

def get_category(db: Session, category_id: int) -> Optional[Category]:
    """ ดึงข้อมูล Category ตาม ID """
    return db.query(Category).filter(Category.id == category_id).first()

def get_category_by_name(db: Session, name: str) -> Optional[Category]:
    """ ดึงข้อมูล Category ตามชื่อ """
    return db.query(Category).filter(Category.name == name).first()

def get_categories(db: Session, skip: int = 0, limit: int = 100) -> Dict[str, Any]:
    """ ดึงข้อมูล Category หลายรายการ พร้อม Pagination Info """
    query = db.query(Category)
    total_count = query.count()
    categories_data = query.order_by(Category.id).offset(skip).limit(limit).all()
    return {"items": categories_data, "total_count": total_count}

def create_category(db: Session, category: schemas.CategoryCreate) -> Category:
    """ สร้าง Category ใหม่ """
    existing_category = get_category_by_name(db, name=category.name)
    if existing_category:
        raise ValueError(f"มีหมวดหมู่ชื่อ '{category.name}' อยู่ในระบบแล้ว")
    db_category = Category(**category.model_dump())
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category

def update_category(db: Session, category_id: int, category_update: schemas.CategoryCreate) -> Optional[Category]:
    """ อัปเดตข้อมูล Category """
    db_category = get_category(db, category_id=category_id)
    if not db_category:
        return None
    if category_update.name != db_category.name:
        existing_category = get_category_by_name(db, name=category_update.name)
        if existing_category and existing_category.id != category_id:
            raise ValueError(f"มีหมวดหมู่ชื่อ '{category_update.name}' อยู่ในระบบแล้ว")
    update_data = category_update.model_dump()
    for key, value in update_data.items():
         setattr(db_category, key, value)
    db.commit()
    db.refresh(db_category)
    return db_category

def delete_category(db: Session, category_id: int) -> Optional[Category]:
    """ ลบ Category (พร้อมตรวจสอบ Dependency) """
    db_category = get_category(db, category_id=category_id)
    if not db_category:
         return None
    linked_product = db.query(Product).filter(Product.category_id == category_id).first()
    if linked_product:
        raise ValueError(f"ไม่สามารถลบหมวดหมู่ '{db_category.name}' ได้ เนื่องจากมีสินค้าผูกอยู่")
    deleted_category_copy = Category(id=db_category.id, name=db_category.name)
    db.delete(db_category)
    db.commit()
    return deleted_category_copy