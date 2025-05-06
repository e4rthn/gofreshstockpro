# services/location_service.py
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

# Absolute Imports
from models import Location, CurrentStock, InventoryTransaction, Sale
import schemas # ใช้ schemas.LocationCreate

def get_location(db: Session, location_id: int) -> Optional[Location]:
    """ ดึงข้อมูล Location ตาม ID """
    return db.query(Location).filter(Location.id == location_id).first()

def get_location_by_name(db: Session, name: str) -> Optional[Location]:
    """ ดึงข้อมูล Location ตามชื่อ """
    return db.query(Location).filter(Location.name == name).first()

def get_locations(db: Session, skip: int = 0, limit: int = 100) -> Dict[str, Any]:
    """ ดึงข้อมูล Location หลายรายการ พร้อม Pagination Info """
    query = db.query(Location)
    total_count = query.count()
    locations_data = query.order_by(Location.id).offset(skip).limit(limit).all()
    return {"items": locations_data, "total_count": total_count}

def create_location(db: Session, location: schemas.LocationCreate) -> Location:
    """ สร้าง Location ใหม่ (รองรับ discount_percent) """
    existing_location = get_location_by_name(db, name=location.name)
    if existing_location:
        raise ValueError(f"มีสถานที่จัดเก็บชื่อ '{location.name}' อยู่ในระบบแล้ว")
    db_location = Location(**location.model_dump())
    db.add(db_location)
    db.commit()
    db.refresh(db_location)
    return db_location

def update_location(db: Session, location_id: int, location_update: schemas.LocationCreate) -> Optional[Location]:
    """ อัปเดตข้อมูล Location (รองรับ discount_percent) """
    db_location = get_location(db, location_id=location_id)
    if not db_location: return None
    if location_update.name != db_location.name:
        existing_location = get_location_by_name(db, name=location_update.name)
        if existing_location and existing_location.id != location_id:
             raise ValueError(f"มีสถานที่จัดเก็บชื่อ '{location_update.name}' อยู่ในระบบแล้ว")
    update_data = location_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
         setattr(db_location, key, value)
    db.commit()
    db.refresh(db_location)
    return db_location

def delete_location(db: Session, location_id: int) -> Optional[Location]:
    """ ลบ Location (พร้อมตรวจสอบ Dependency) """
    db_location = db.query(Location).filter(Location.id == location_id).first()
    if not db_location: return None
    if db.query(CurrentStock).filter(CurrentStock.location_id == location_id).first():
        raise ValueError(f"ไม่สามารถลบสถานที่ '{db_location.name}' ได้ เนื่องจากมีข้อมูลสต็อกคงเหลืออยู่")
    if db.query(InventoryTransaction).filter(InventoryTransaction.location_id == location_id).first():
         raise ValueError(f"ไม่สามารถลบสถานที่ '{db_location.name}' ได้ เนื่องจากมีประวัติ Transaction เกี่ยวข้อง")
    if db.query(Sale).filter(Sale.location_id == location_id).first():
        raise ValueError(f"ไม่สามารถลบสถานที่ '{db_location.name}' ได้ เนื่องจากมีประวัติการขายเกี่ยวข้อง")
    deleted_location_copy = Location(
        id=db_location.id, name=db_location.name,
        description=db_location.description, discount_percent=db_location.discount_percent
    )
    db.delete(db_location)
    db.commit()
    return deleted_location_copy