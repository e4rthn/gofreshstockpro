# gofresh_stockpro/schemas/inventory.py
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any 
from datetime import date

# --- StockInSchema เดิม (อาจจะยังเก็บไว้ถ้ามีการใช้งานที่อื่น) ---
class StockInSchema(BaseModel):
    product_id: int
    location_id: int
    quantity: float = Field(..., gt=0)
    cost_per_unit: Optional[float] = None
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None
    notes: Optional[str] = None

# --- Schemas ใหม่สำหรับ Batch Stock-In ---
class StockInItemDetailSchema(BaseModel):
    product_id: int
    quantity: float = Field(..., gt=0)
    cost_per_unit: Optional[float] = Field(None, ge=0)
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None # สามารถกรอกโดยตรง หรือคำนวณจาก production_date + shelf_life
    notes: Optional[str] = None
    
    # Optional fields for client-side display convenience (ไม่จำเป็นต้องส่งไป backend ทั้งหมด)
    # These might be populated by JS when building the review page or batch list
    product_name: Optional[str] = None 
    product_sku: Optional[str] = None
    shelf_life_days: Optional[int] = None 

class BatchStockInSchema(BaseModel):
    location_id: int = Field(...)
    items: List[StockInItemDetailSchema] = Field(..., min_length=1)
    batch_notes: Optional[str] = None # หมายเหตุรวมสำหรับ Batch นี้ (ถ้ามี)

# --- StockAdjustmentSchema (เหมือนเดิม) ---
class StockAdjustmentSchema(BaseModel):
    product_id: int
    location_id: int
    quantity_change: float = Field(...) 
    reason: Optional[str] = None
    notes: Optional[str] = None

# --- StockTransferSchema (เหมือนเดิม) ---
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