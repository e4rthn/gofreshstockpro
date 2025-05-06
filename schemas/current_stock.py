# schemas/current_stock.py
from pydantic import BaseModel
from datetime import datetime

# Relative import สำหรับ schema อื่น
from .product import Product as ProductSchema
from .location import Location as LocationSchema

class CurrentStock(BaseModel):
    id: int
    quantity: int
    last_updated: datetime
    product: ProductSchema
    location: LocationSchema

    class Config:
        from_attributes = True