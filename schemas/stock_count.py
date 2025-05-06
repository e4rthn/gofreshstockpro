# schemas/stock_count.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# --- Absolute Import สำหรับ Enum ---
from models import StockCountStatus
# -----------------------------------
# Relative import
from .location import Location
from .product import ProductBasic

# --- Stock Count Item Schemas ---
class StockCountItemBase(BaseModel):
    product_id: int
    system_quantity: int
    counted_quantity: Optional[int] = None

class StockCountItemCreate(BaseModel):
    product_id: int = Field(...)

class StockCountItemUpdate(BaseModel):
    counted_quantity: int = Field(..., ge=0)

class StockCountItem(StockCountItemBase):
    id: int
    session_id: int
    difference: Optional[int] = None
    count_date: Optional[datetime] = None
    product: Optional[ProductBasic] = None
    class Config: from_attributes = True

# --- Stock Count Session Schemas ---
class StockCountSessionBase(BaseModel):
    location_id: int
    notes: Optional[str] = None

class StockCountSessionCreate(StockCountSessionBase):
    pass

class StockCountSessionUpdate(BaseModel):
     status: Optional[StockCountStatus] = None
     notes: Optional[str] = None
     end_date: Optional[datetime] = None

class StockCountSession(StockCountSessionBase):
    id: int
    start_date: datetime
    end_date: Optional[datetime] = None
    status: StockCountStatus
    location: Optional[Location] = None
    items: List[StockCountItem] = []
    class Config: from_attributes = True

class StockCountSessionInList(StockCountSessionBase):
     id: int
     start_date: datetime
     end_date: Optional[datetime] = None
     status: StockCountStatus
     location: Optional[Location] = None
     class Config: from_attributes = True