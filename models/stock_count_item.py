# models/stock_count_item.py
from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base # Absolute Import

class StockCountItem(Base):
    __tablename__ = "stock_count_items"
    id = Column(Integer, primary_key=True, index=True)
    system_quantity = Column(Integer, nullable=False)
    counted_quantity = Column(Integer, nullable=True)
    count_date = Column(DateTime(timezone=True), nullable=True)
    session_id = Column(Integer, ForeignKey("stock_count_sessions.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)

    session = relationship("StockCountSession", back_populates="items")
    product = relationship("Product", back_populates="stock_count_items") # เพิ่ม back_populates
    @property
    def difference(self):
         if self.counted_quantity is not None and self.system_quantity is not None:
              return self.counted_quantity - self.system_quantity
         return None
    def __repr__(self):
        return f"<StockCountItem(session={self.session_id}, product={self.product_id}, counted={self.counted_quantity})>"