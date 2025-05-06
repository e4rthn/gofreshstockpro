# schemas/sale.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# Relative import
from .product import ProductBasic
from .location import Location

# --- Sale Item Schemas ---
class SaleItemBase(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)
    unit_price: float # ราคาขายจริงต่อหน่วย (หลังหักส่วนลด RTC ถ้ามี)
    # --- Fields สำหรับ RTC (เป็น Optional ตอนสร้าง) ---
    is_rtc: Optional[bool] = Field(False, description="สินค้านี้เป็นราคา RTC หรือไม่")
    original_unit_price: Optional[float] = Field(None, description="ราคาเต็มก่อนลด (ถ้า is_rtc=True)")
    discount_amount: Optional[float] = Field(None, ge=0, description="ส่วนลดต่อหน่วย (ถ้า is_rtc=True และมีส่วนลด)")
    # ---------------------------------------------------

class SaleItemCreate(SaleItemBase):
    pass

class SaleItem(SaleItemBase):
    id: int
    # คำนวณ total_price จาก property ใน model หรือเพิ่ม field ถ้าเก็บใน DB
    # ถ้า model มี property ชื่อ total_price, Pydantic จะเรียกใช้ตอนแปลง
    total_price: float # หรือ Decimal

    product: Optional[ProductBasic] = None # แสดงข้อมูล product ย่อ

    class Config:
        from_attributes = True

# --- Sale Schemas ---
class SaleBase(BaseModel):
    location_id: int
    notes: Optional[str] = None

class SaleCreate(SaleBase):
    items: List[SaleItemCreate] = Field(..., min_length=1)

class Sale(SaleBase):
    id: int
    sale_date: datetime
    total_amount: float # หรือ Decimal
    items: List[SaleItem]
    location: Location # ใช้ Location schema ที่ import มา

    class Config:
        from_attributes = True