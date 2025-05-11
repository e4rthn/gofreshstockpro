# gofresh_stockpro/schemas/product.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Annotated # Annotated import ถูกต้องแล้ว
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
    # การใช้ Annotated ใน Type Hint ของ field แบบนี้ถูกต้อง
    shelf_life_days: Optional[Annotated[int, Field(ge=0)]] = None

    @validator('barcode', pre=True, always=True)
    def empty_str_barcode_to_none(cls, v):
        if v == "":
            return None
        return v

class ProductCreate(ProductBase):
    pass # สืบทอด field ทั้งหมดมาจาก ProductBase

class ProductUpdate(ProductBase):
    # กำหนด field ทั้งหมดเป็น Optional เพื่อให้สามารถอัปเดตบางส่วนได้
    # และ type hint ตรงนี้จะ override ของ ProductBase
    sku: Optional[str] = None
    name: Optional[str] = None
    barcode: Optional[str] = None # validator จาก ProductBase จะยังทำงาน
    description: Optional[str] = None
    price_b2c: Optional[float] = Field(None, gt=0)
    price_b2b: Optional[float] = Field(None, gt=0)
    standard_cost: Optional[float] = Field(None, ge=0)
    image_url: Optional[str] = None
    category_id: Optional[int] = None
    shelf_life_days: Optional[Annotated[int, Field(ge=0)]] = None # การใช้ Annotated ที่นี่ก็ถูกต้อง

    # validator ของ barcode ใน ProductUpdate อาจจะไม่จำเป็น
    # เพราะ ProductBase มี validator อยู่แล้ว และ ProductUpdate kế thừaมา
    # แต่ถ้าต้องการ logic ที่ต่างกันจริงๆ ก็สามารถคงไว้ได้
    # ในที่นี้ validator ของ ProductBase น่าจะครอบคลุมแล้ว
    # @validator('barcode', pre=True, always=True)
    # def empty_str_barcode_update_to_none(cls, v):
    #      if v == "":
    #          return None
    #      return v

class Product(ProductBase): # Schema สำหรับอ่านข้อมูล Product (รวม Category)
    id: int
    category: CategorySchema # แสดงข้อมูล Category ที่เชื่อมโยงกัน

    class Config:
        from_attributes = True # หรือ orm_mode = True สำหรับ Pydantic V1

class ProductBasic(BaseModel): # Schema สำหรับแสดงข้อมูล Product แบบย่อ (เช่น ใน Dropdown)
    id: int
    name: str
    sku: str
    barcode: Optional[str] = None
    price_b2c: Optional[float] = None # อาจจะเป็นประโยชน์ใน POS
    standard_cost: Optional[float] = None # อาจจะเป็นประโยชน์
    shelf_life_days: Optional[int] = None # สำหรับ Stock In form

    class Config:
        from_attributes = True