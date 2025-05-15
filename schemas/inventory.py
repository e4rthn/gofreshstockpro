# schemas/inventory.py
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from datetime import date

# Schema สำหรับ Stock In (ปรับปรุง)
class StockInSchema(BaseModel):
    product_id: int
    location_id: int
    quantity: float = Field(..., gt=0)
    cost_per_unit: Optional[float] = None
    # --- เปลี่ยนจาก expiry_date เป็น production_date ---
    production_date: Optional[date] = None # วันที่ผลิต (ถ้ามี)
    # --- expiry_date กลายเป็น Optional (เผื่อกรอกตรง หรือไม่มี shelf life) ---
    expiry_date: Optional[date] = None     # วันหมดอายุ (ถ้าต้องการกรอกโดยตรง)
    # ---------------------------------------------------
    notes: Optional[str] = None

    # การ validate ที่ซับซ้อนว่าต้องกรอก date อย่างน้อย 1 อย่าง (ขึ้นกับ shelf life)
    # ควรทำใน service layer เพื่อให้เข้าถึงข้อมูล product ได้
    # @validator('expiry_date', always=True)
    # def check_expiry_or_production_date(cls, v, values):
    #     production_date = values.get('production_date')
    #     # if not production_date and not v:
    #     #     raise ValueError('ต้องระบุ Production Date หรือ Expiry Date อย่างใดอย่างหนึ่ง')
    #     return v


# Schema สำหรับ Stock Adjustment (เหมือนเดิม)
class StockAdjustmentSchema(BaseModel):
    product_id: int
    location_id: int
    quantity_change: float = Field(...) # เช็ค not-zero ใน route/service
    reason: Optional[str] = None
    notes: Optional[str] = None

# Schema สำหรับ Stock Transfer (เหมือนเดิม)
class StockTransferSchema(BaseModel):
    product_id: int
    from_location_id: int
    to_location_id: int
    quantity: float = Field(..., gt=0)
    notes: Optional[str] = None

    @validator('to_location_id')
    def locations_must_be_different(cls, v: int, values: Dict[str, Any]) -> int:
        if 'from_location_id' in values and v == values['from_location_id']:
            raise ValueError('สถานที่จัดเก็บต้นทางและปลายทางต้องแตกต่างกัน')
        return v