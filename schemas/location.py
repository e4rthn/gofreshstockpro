# schemas/location.py
from pydantic import BaseModel, Field
from typing import Optional

class LocationBase(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    discount_percent: Optional[float] = Field(None, ge=0, le=100)

class LocationCreate(LocationBase):
    pass

class Location(LocationBase):
    id: int

    class Config:
        from_attributes = True