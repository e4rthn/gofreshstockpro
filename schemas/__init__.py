# schemas/__init__.py
from .category import Category, CategoryBase, CategoryCreate
from .product import Product, ProductBase, ProductCreate, ProductBasic
from .location import Location, LocationBase, LocationCreate
from .current_stock import CurrentStock
from .inventory_transaction import (
    InventoryTransaction,
    InventoryTransactionBase,
    InventoryTransactionCreate
)
from .inventory import StockInSchema, StockAdjustmentSchema, StockTransferSchema
from .sale import Sale, SaleBase, SaleCreate, SaleItem, SaleItemBase, SaleItemCreate
from .stock_count import (
    StockCountSession, StockCountSessionBase, StockCountSessionCreate, StockCountSessionUpdate,
    StockCountItem, StockCountItemBase, StockCountItemCreate, StockCountItemUpdate,
    StockCountSessionInList
)

# --- ใช้ Absolute Import สำหรับ Enums จาก models ---
from models import TransactionType, StockCountStatus
# -------------------------------------------------