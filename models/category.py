# models/category.py
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from database import Base # Absolute Import

class Category(Base): # <--- นี่คือ SQLAlchemy Model เท่านั้น
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    products = relationship("Product", back_populates="category")
    def __repr__(self): return f"<Category(id={self.id}, name='{self.name}')>"