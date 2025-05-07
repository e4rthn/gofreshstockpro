# schemas/dashboard.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime # Ensure datetime is imported

class KpiSummarySchema(BaseModel):
    """ Schema for Key Performance Indicators """
    today_sales_total: float = 0.0
    today_sales_count: int = 0
    negative_stock_item_count: int = 0
    near_expiry_item_count: int = 0

class SalesTrendItemSchema(BaseModel):
    """ Schema for one item in the sales trend data list """
    date: date
    total_sales: float = 0.0

class ProductPerformanceItemSchema(BaseModel):
    """ Schema for top/low performing products """
    product_id: int
    product_name: str
    product_sku: str
    value: float # Could be total sales amount or quantity sold/remaining

class CategoryDistributionItemSchema(BaseModel):
    """ Schema for category distribution """
    category_id: int
    category_name: str
    value: float # Could be count, stock quantity sum, or stock value sum

class RecentTransactionItemSchema(BaseModel):
     """ Schema for displaying recent transactions (simplified) """
     id: int
     transaction_date: datetime # Use the imported datetime class
     transaction_type: str
     product_name: str
     location_name: str
     quantity_change: int
     notes: Optional[str] = None

     class Config:
         from_attributes = True # orm_mode = True for Pydantic v1