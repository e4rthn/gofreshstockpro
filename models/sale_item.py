# models/sale_item.py
from sqlalchemy import Column, Integer, Float, ForeignKey, Boolean # เพิ่ม Boolean
from sqlalchemy.orm import relationship
from database import Base # Absolute Import

class SaleItem(Base):
    __tablename__ = "sale_items"
    id = Column(Integer, primary_key=True, index=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    original_unit_price = Column(Float, nullable=True)       # Field สำหรับ RTC
    discount_amount = Column(Float, nullable=True, default=0.0) # Field สำหรับ RTC
    is_rtc = Column(Boolean, nullable=False, default=False, server_default="false") # Field สำหรับ RTC

    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)

    sale = relationship("Sale", back_populates="items")
    product = relationship("Product", back_populates="sale_items") # เพิ่ม back_populates
    @property
    def total_price(self): return self.quantity * self.unit_price
    def __repr__(self):
         return f"<SaleItem(sale_id={self.sale_id}, product_id={self.product_id}, qty={self.quantity}, price={self.unit_price})>"