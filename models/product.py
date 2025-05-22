# models/product.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from database import Base
import datetime

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True, nullable=False)
    barcode = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    standard_cost = Column(Float, nullable=True)
    price_b2c = Column(Float, nullable=False)
    price_b2b = Column(Float, nullable=True)
    image_url = Column(String, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    shelf_life_days = Column(Integer, nullable=True)

    # For B2C price tracking
    previous_price_b2c = Column(Float, nullable=True)
    price_b2c_last_changed = Column(DateTime(timezone=True), nullable=True)

    # For B2B price tracking
    previous_price_b2b = Column(Float, nullable=True)
    price_b2b_last_changed = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    category = relationship("Category", back_populates="products")
    current_stocks = relationship("CurrentStock", back_populates="product", cascade="all, delete-orphan")
    inventory_transactions = relationship("InventoryTransaction", back_populates="product")
    sale_items = relationship("SaleItem", back_populates="product")
    stock_count_items = relationship("StockCountItem", back_populates="product")

    def __repr__(self):
        return f"<Product(id={self.id}, sku='{self.sku}', name='{self.name}', barcode='{self.barcode}')>"