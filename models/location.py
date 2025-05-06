# models/location.py
from sqlalchemy import Column, Integer, String, Text, Float, ForeignKey
from sqlalchemy.orm import relationship
from database import Base # Absolute Import

class Location(Base):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    discount_percent = Column(Float, nullable=True)

    current_stocks = relationship("CurrentStock", back_populates="location")
    inventory_transactions = relationship("InventoryTransaction", back_populates="location")
    sales = relationship("Sale", back_populates="location")
    stock_count_sessions = relationship("StockCountSession", back_populates="location")

    def __repr__(self):
        return f"<Location(id={self.id}, name='{self.name}')>"