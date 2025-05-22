# schemas/dashboard.py
from pydantic import BaseModel, Field # Field อาจจะไม่จำเป็นถ้าไม่ได้ใช้ validation พิเศษที่นี่
from typing import List, Optional
from datetime import date, datetime # Ensure datetime is imported for all necessary fields

class KpiSummarySchema(BaseModel):
    """ Schema for Key Performance Indicators """
    today_sales_total: float = 0.0
    today_sales_count: int = 0
    negative_stock_item_count: int = 0
    near_expiry_item_count: int = 0

    class Config:
        from_attributes = True # orm_mode = True for Pydantic v1

class SalesTrendItemSchema(BaseModel):
    """ Schema for one item in the sales trend data list """
    date: date # Should be just date, not datetime, for daily trend
    total_sales: float = 0.0

    class Config:
        from_attributes = True

class ProductPerformanceItemSchema(BaseModel):
    """ Schema for top/low performing products """
    product_id: int
    product_name: str
    product_sku: str
    value: float # Could be total sales amount or quantity sold/remaining

    class Config:
        from_attributes = True

class CategoryDistributionItemSchema(BaseModel):
    """ Schema for category distribution """
    category_id: int
    category_name: str
    value: float # Could be count, stock quantity sum, or stock value sum

    class Config:
        from_attributes = True

class RecentTransactionItemSchema(BaseModel):
     """ Schema for displaying recent transactions (simplified) """
     id: int
     transaction_date: datetime # Use the imported datetime class
     transaction_type: str      # This will be the string representation of the Enum
     product_name: str
     location_name: str
     quantity_change: float     # <<< แก้ไขจาก int เป็น float
     notes: Optional[str] = None

     class Config:
         from_attributes = True # orm_mode = True for Pydantic v1