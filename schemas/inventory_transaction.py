# schemas/inventory_transaction.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date

# --- Absolute Import สำหรับ Enum ---
from models import TransactionType
# -----------------------------------
# Relative import สำหรับ schema อื่น
from .product import Product as ProductSchema
from .location import Location as LocationSchema

class InventoryTransactionBase(BaseModel):
    product_id: int
    location_id: int
    quantity_change: int
    notes: Optional[str] = None
    cost_per_unit: Optional[float] = None
    expiry_date: Optional[date] = None
    # --- เพิ่ม production_date ---
    production_date: Optional[date] = None
    # ---------------------------
    related_transaction_id: Optional[int] = None

class InventoryTransactionCreate(InventoryTransactionBase):
    transaction_type: TransactionType # ใช้ Enum ที่ import มา

class InventoryTransaction(InventoryTransactionBase):
    id: int
    transaction_type: TransactionType
    transaction_date: datetime
    product: ProductSchema
    location: LocationSchema

    class Config:
        from_attributes = True