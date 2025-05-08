# routers/locations.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

# Adjust imports
import schemas
from services import location_service
from database import get_db

API_INCLUDE_IN_SCHEMA = True

# API Router (Prefix defined in main.py)
router = APIRouter(
    tags=["API - สถานที่จัดเก็บ"],
    include_in_schema=API_INCLUDE_IN_SCHEMA
)

# --- API Routes Only ---
@router.post("/", response_model=schemas.Location, status_code=status.HTTP_201_CREATED)
async def api_create_new_location(location: schemas.LocationCreate, db: Session = Depends(get_db)):
    """สร้างสถานที่จัดเก็บใหม่ (API)"""
    try:
        return location_service.create_location(db=db, location=location)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@router.get("/", response_model=List[schemas.Location])
async def api_read_all_locations(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """ดึงรายการสถานที่จัดเก็บทั้งหมด (API)"""
    locations_data = location_service.get_locations(db, skip=skip, limit=limit)
    return locations_data.get("items", [])

@router.get("/{location_id}", response_model=schemas.Location)
async def api_read_one_location(location_id: int, db: Session = Depends(get_db)):
    """ดึงข้อมูลสถานที่จัดเก็บตามรหัส (API)"""
    db_location = location_service.get_location(db, location_id=location_id)
    if db_location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสถานที่จัดเก็บรหัส {location_id}")
    return db_location

@router.put("/{location_id}", response_model=schemas.Location)
async def api_update_existing_location(location_id: int, location: schemas.LocationCreate, db: Session = Depends(get_db)):
    """อัปเดตข้อมูลสถานที่จัดเก็บ (API)"""
    try:
        updated_loc = location_service.update_location(db, location_id=location_id, location_update=location)
        if updated_loc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสถานที่รหัส {location_id}")
        return updated_loc
    except ValueError as e: # Handle name conflict
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        print(f"Unexpected error updating location {location_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error while updating location.")


@router.delete("/{location_id}", response_model=schemas.Location)
async def api_remove_location(location_id: int, db: Session = Depends(get_db)):
    """ลบสถานที่จัดเก็บ (API)"""
    try:
        deleted_loc = location_service.delete_location(db, location_id=location_id)
        if deleted_loc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสถานที่รหัส {location_id}")
        # Service returns the deleted model object, FastAPI serializes it
        return deleted_loc
    except ValueError as e: # Handle dependency error
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(f"Unexpected error deleting location {location_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error while deleting location.")

# --- No UI Routes Here Anymore ---