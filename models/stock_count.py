# models/stock_count.py
import enum
from sqlalchemy import (Column, Integer, String, ForeignKey, DateTime,
                        Text, Enum as SQLAlchemyEnum)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base # Absolute Import

class StockCountStatus(str, enum.Enum):
    OPEN = "OPEN"
    COUNTING = "COUNTING"
    CLOSED = "CLOSED"
    CANCELED = "CANCELED"

class StockCountSession(Base):
    __tablename__ = "stock_count_sessions"
    id = Column(Integer, primary_key=True, index=True)
    start_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    end_date = Column(DateTime(timezone=True), nullable=True, index=True)
    status = Column(SQLAlchemyEnum(StockCountStatus, name="stockcountstatusenum"), nullable=False, default=StockCountStatus.OPEN, index=True) # ใส่ name ให้ Enum
    notes = Column(Text, nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)

    location = relationship("Location", back_populates="stock_count_sessions") # เพิ่ม back_populates
    items = relationship("StockCountItem", back_populates="session", cascade="all, delete-orphan")
    def __repr__(self):
        return f"<StockCountSession(id={self.id}, location_id={self.location_id}, status='{self.status.value}')>"