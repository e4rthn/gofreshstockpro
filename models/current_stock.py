# models/current_stock.py
from sqlalchemy import (Column, Integer, Float, ForeignKey, DateTime,
                        UniqueConstraint)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base # Absolute Import

class CurrentStock(Base):
    __tablename__ = "current_stock"
    id = Column(Integer, primary_key=True, index=True)
    quantity = Column(Integer, nullable=False, default=0)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)

    product = relationship("Product", back_populates="current_stocks")
    location = relationship("Location", back_populates="current_stocks")
    __table_args__ = (UniqueConstraint('product_id', 'location_id', name='uq_product_location'),)
    def __repr__(self):
        return f"<CurrentStock(product_id={self.product_id}, location_id={self.location_id}, quantity={self.quantity})>"