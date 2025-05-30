# schemas/__init__.py
from .category import Category, CategoryBase, CategoryCreate
from .product import Product, ProductBase, ProductCreate, ProductUpdate, ProductBasic
from .location import Location, LocationBase, LocationCreate
from .current_stock import CurrentStock
from .inventory_transaction import (
    InventoryTransaction,
    InventoryTransactionBase,
    InventoryTransactionCreate
)
from .inventory import ( # แก้ไขส่วนนี้
    StockInSchema, 
    StockAdjustmentSchema, 
    StockTransferSchema,
    StockInItemDetailSchema,  # <--- ที่เพิ่มเข้ามา
    BatchStockInSchema        # <--- ที่เพิ่มเข้ามา
)
from .sale import Sale, SaleBase, SaleCreate, SaleItem, SaleItemBase, SaleItemCreate
from .stock_count import (
    StockCountSession, StockCountSessionBase, StockCountSessionCreate, StockCountSessionUpdate,
    StockCountItem, StockCountItemBase, StockCountItemCreate, StockCountItemUpdate,
    StockCountSessionInList
)
# --- Add Dashboard Schemas ---
from .dashboard import ( 
    KpiSummarySchema,
    SalesTrendItemSchema,
    ProductPerformanceItemSchema,
    CategoryDistributionItemSchema,
    RecentTransactionItemSchema
)