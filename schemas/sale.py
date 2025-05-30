# schemas/sale.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from .product import ProductBasic
from .location import Location

class SaleItemBase(BaseModel):
    product_id: int
    quantity: float = Field(..., gt=0)  # <--- แก้ไข: int -> float
    unit_price: float
    is_rtc: Optional[bool] = Field(False, description="สินค้านี้เป็นราคา RTC หรือไม่")
    original_unit_price: Optional[float] = Field(None, description="ราคาเต็มก่อนลด (ถ้า is_rtc=True)")
    discount_amount: Optional[float] = Field(None, ge=0, description="ส่วนลดต่อหน่วย (ถ้า is_rtc=True และมีส่วนลด)")

class SaleItemCreate(SaleItemBase):
    pass

class SaleItem(SaleItemBase):
    id: int
    total_price: float
    product: Optional[ProductBasic] = None

    class Config:
        from_attributes = True

class SaleBase(BaseModel):
    location_id: int
    notes: Optional[str] = None

class SaleCreate(SaleBase):
    items: List[SaleItemCreate] = Field(..., min_length=1)

class Sale(SaleBase):
    id: int
    sale_date: datetime
    total_amount: float
    items: List[SaleItem]
    location: Location # ใช้ Location schema ที่ import มา

    class Config:
        from_attributes = True