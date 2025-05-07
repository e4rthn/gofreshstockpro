# schemas/product.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List

from .category import Category as CategorySchema # Assuming Category schema is correctly defined and imported

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

    @validator('barcode', pre=True, always=True) # pre=True to modify before other validations
    def empty_str_barcode_to_none(cls, v):
        if v == "":
            return None
        return v

class ProductCreate(ProductBase):
    pass

class ProductUpdate(ProductBase): # This is the schema that was missing or not exported
    sku: Optional[str] = None
    name: Optional[str] = None
    # barcode is Optional[str] = None inherited from ProductBase
    description: Optional[str] = None
    price_b2c: Optional[float] = Field(None, gt=0)
    price_b2b: Optional[float] = Field(None, gt=0)
    standard_cost: Optional[float] = Field(None, ge=0)
    image_url: Optional[str] = None
    category_id: Optional[int] = None

class Product(ProductBase): # For reading product data
    id: int
    category: CategorySchema # This should be the Pydantic Category schema

    class Config:
        from_attributes = True # orm_mode for Pydantic v1

class ProductBasic(BaseModel): # For concise product listings or lookups
    id: int
    name: str
    sku: str
    barcode: Optional[str] = None # Added barcode
    price_b2c: Optional[float] = None # Ensure this is available for POS
    standard_cost: Optional[float] = None

    class Config:
        from_attributes = True