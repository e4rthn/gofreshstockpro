# schemas/inventory.py
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from datetime import date

# Schema สำหรับ Stock In
class StockInSchema(BaseModel):
    product_id: int
    location_id: int
    quantity: int = Field(..., gt=0)
    cost_per_unit: Optional[float] = None
    expiry_date: Optional[date] = None
    notes: Optional[str] = None

# Schema สำหรับ Stock Adjustment
class StockAdjustmentSchema(BaseModel):
    product_id: int
    location_id: int
    quantity_change: int = Field(...) # เช็ค not-zero ใน route/service
    reason: Optional[str] = None
    notes: Optional[str] = None

# Schema สำหรับ Stock Transfer
class StockTransferSchema(BaseModel):
    product_id: int
    from_location_id: int
    to_location_id: int
    quantity: int = Field(..., gt=0)
    notes: Optional[str] = None

    @validator('to_location_id')
    def locations_must_be_different(cls, v: int, values: Dict[str, Any]) -> int:
        # values จะเป็น dict ที่มี from_location_id ถ้ามันถูกประกาศก่อน to_location_id ใน Model
        if 'from_location_id' in values and v == values['from_location_id']:
            raise ValueError('สถานที่จัดเก็บต้นทางและปลายทางต้องแตกต่างกัน')
        return v