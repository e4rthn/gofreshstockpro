# schemas/inventory_transaction.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date

from models import TransactionType
from .product import Product as ProductSchema
from .location import Location as LocationSchema

class InventoryTransactionBase(BaseModel):
    product_id: int
    location_id: int
    quantity_change: float  # <--- แก้ไข: int -> float
    notes: Optional[str] = None
    cost_per_unit: Optional[float] = None
    expiry_date: Optional[date] = None
    production_date: Optional[date] = None
    related_transaction_id: Optional[int] = None

class InventoryTransactionCreate(InventoryTransactionBase):
    transaction_type: TransactionType

class InventoryTransaction(InventoryTransactionBase):
    id: int
    transaction_type: TransactionType # Type นี้ถูกใช้ใน Enum แล้ว ซึ่งถูกต้อง
    transaction_date: datetime
    product: ProductSchema
    location: LocationSchema

    class Config:
        from_attributes = True