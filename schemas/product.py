# แก้ไขไฟล์: gofresh_stockpro/schemas/product.py
# เพิ่ม Annotated จาก typing และ Field จาก pydantic (ถ้ายังไม่มี Field)
from pydantic import BaseModel, Field, validator, conint
from typing import Optional, List, Annotated # <--- เพิ่ม Annotated
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
    # --- แก้ไข shelf_life_days ให้ใช้ Annotated ---
    shelf_life_days: Optional[Annotated[int, Field(ge=0)]] = None # <--- แก้ไขบรรทัดนี้
    # -------------------------------------------

    @validator('barcode', pre=True, always=True)
    def empty_str_barcode_to_none(cls, v):
        if v == "":
            return None
        return v

class ProductCreate(ProductBase):
    pass

class ProductUpdate(ProductBase):
    sku: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    price_b2c: Optional[float] = Field(None, gt=0)
    price_b2b: Optional[float] = Field(None, gt=0)
    standard_cost: Optional[float] = Field(None, ge=0)
    image_url: Optional[str] = None
    category_id: Optional[int] = None
    # --- แก้ไข shelf_life_days ให้ใช้ Annotated ---
    shelf_life_days: Optional[Annotated[int, Field(ge=0)]] = None # <--- แก้ไขบรรทัดนี้
    # -------------------------------------------

    # หมายเหตุ: validator ของ barcode ใน ProductUpdate อาจจะไม่จำเป็นแล้ว
    # เพราะ ProductBase มี validator อยู่แล้ว และ ProductUpdate kế thừaมา
    # แต่ถ้าต้องการ logic ที่ต่างกัน ก็สามารถคงไว้ได้
    @validator('barcode', pre=True, always=True)
    def empty_str_barcode_update_to_none(cls, v):
         if v == "":
             return None
         return v

class Product(ProductBase): # For reading product data
    id: int
    category: CategorySchema
    class Config: from_attributes = True

class ProductBasic(BaseModel): # For concise product listings or lookups
    id: int
    name: str
    sku: str
    barcode: Optional[str] = None
    price_b2c: Optional[float] = None
    standard_cost: Optional[float] = None
    shelf_life_days: Optional[int] = None # ส่วนนี้ไม่ต้องใช้ Annotated เพราะเป็นการอ่านข้อมูล ไม่ใช่ validation input
    class Config: from_attributes = True