# models/sale.py
from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base # Absolute Import

class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True, index=True)
    sale_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    total_amount = Column(Float, nullable=False)
    notes = Column(Text, nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)

    location = relationship("Location", back_populates="sales") # เพิ่ม back_populates
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
    def __repr__(self):
        return f"<Sale(id={self.id}, location_id={self.location_id}, total={self.total_amount})>"