# models/inventory_transaction.py
import enum
from sqlalchemy import (Column, Integer, String, Float, ForeignKey, DateTime,
                        Text, Date, Enum as SQLAlchemyEnum)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base # Absolute Import

# --- Python Enum Definition ---
class TransactionType(str, enum.Enum):
    STOCK_IN = "STOCK_IN"
    SALE = "SALE"
    ADJUSTMENT_ADD = "ADJUSTMENT_ADD"
    ADJUSTMENT_SUB = "ADJUSTMENT_SUB"
    TRANSFER_OUT = "TRANSFER_OUT"
    TRANSFER_IN = "TRANSFER_IN"
    INITIAL = "INITIAL"

# --- SQLAlchemy Model Definition ---
class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"

    id = Column(Integer, primary_key=True, index=True)

    transaction_type = Column(
        SQLAlchemyEnum(
            TransactionType,
            name="transactiontypeenum", # <--- แก้ไขตรงนี้ให้ตรงกับ Alembic
            native_enum=True,
            create_constraint=True
        ),
        nullable=False,
        index=True
    )

    quantity_change = Column(Float, nullable=False) # ตรงนี้เป็น Float ซึ่งถูกต้อง
    transaction_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    notes = Column(Text, nullable=True)
    cost_per_unit = Column(Float, nullable=True)
    expiry_date = Column(Date, nullable=True)
    production_date = Column(Date, nullable=True)
    related_transaction_id = Column(Integer, nullable=True, index=True)

    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)

    product = relationship("Product", back_populates="inventory_transactions")
    location = relationship("Location", back_populates="inventory_transactions")

    def __repr__(self):
        return (f"<InventoryTransaction(id={self.id}, "
                f"type={self.transaction_type.value if self.transaction_type else 'None'}, "
                f"product_id={self.product_id}, "
                f"qty_change={self.quantity_change})>")