# gofresh_stockpro/schemas/product.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Annotated
from datetime import datetime
from .category import Category as CategorySchema

class ProductBase(BaseModel):
    sku: str
    name: str
    barcode: Optional[str] = None
    description: Optional[str] = None
    price_b2c: float = Field(..., gt=0)
    price_b2b: Optional[float] = Field(None, gt=0)
    standard_cost: Optional[float] = Field(None, ge=0)
    image_url: Optional[str] = None
    category_id: int
    shelf_life_days: Optional[Annotated[int, Field(ge=0)]] = None

    # For B2C price tracking (optional when reading)
    previous_price_b2c: Optional[float] = None
    price_b2c_last_changed: Optional[datetime] = None

    # For B2B price tracking (optional when reading)
    previous_price_b2b: Optional[float] = None
    price_b2b_last_changed: Optional[datetime] = None

    @validator('barcode', pre=True, always=True)
    def empty_str_barcode_to_none(cls, v):
        if v == "":
            return None
        return v

class ProductCreate(ProductBase):
    # Exclude history fields from creation payload
    previous_price_b2c: Optional[float] = Field(None, exclude=True)
    price_b2c_last_changed: Optional[datetime] = Field(None, exclude=True)
    previous_price_b2b: Optional[float] = Field(None, exclude=True)
    price_b2b_last_changed: Optional[datetime] = Field(None, exclude=True)
    pass

class ProductUpdate(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    barcode: Optional[str] = None
    description: Optional[str] = None
    price_b2c: Optional[float] = Field(None, gt=0)
    price_b2b: Optional[float] = Field(None, gt=0)
    standard_cost: Optional[float] = Field(None, ge=0)
    image_url: Optional[str] = None
    category_id: Optional[int] = None
    shelf_life_days: Optional[Annotated[int, Field(ge=0)]] = None
    # History fields are managed by the server, not updated by client

    @validator('barcode', pre=True, always=True)
    def empty_str_barcode_update_to_none(cls, v):
        if v == "":
            return None
        return v

class Product(ProductBase): # Schema for reading Product (includes all fields from ProductBase)
    id: int
    category: CategorySchema

    class Config:
        from_attributes = True

class ProductBasic(BaseModel): # Schema for simpler product display (e.g., dropdowns)
    id: int
    name: str
    sku: str
    barcode: Optional[str] = None
    price_b2c: Optional[float] = None
    price_b2b: Optional[float] = None
    standard_cost: Optional[float] = None
    shelf_life_days: Optional[int] = None
    # You might add previous_price fields here if a basic view needs them,
    # but the catalog page uses the full 'Product' schema.

    class Config:
        from_attributes = True