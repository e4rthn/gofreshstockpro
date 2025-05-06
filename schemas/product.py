# schemas/product.py
from pydantic import BaseModel, Field
from typing import Optional, List

# Relative import สำหรับ schema ใน package เดียวกัน
from .category import Category as CategorySchema

class ProductBase(BaseModel):
    sku: str
    name: str
    description: Optional[str] = None
    price_b2c: float = Field(..., gt=0)
    price_b2b: Optional[float] = Field(None, gt=0)
    standard_cost: Optional[float] = Field(None, ge=0)
    image_url: Optional[str] = None
    category_id: int

class ProductCreate(ProductBase):
    pass

class Product(ProductBase):
    id: int
    category: CategorySchema

    class Config:
        from_attributes = True

class ProductBasic(BaseModel):
    id: int
    name: str
    sku: str
    price_b2c: Optional[float] = None
    standard_cost: Optional[float] = None

    class Config:
        from_attributes = True