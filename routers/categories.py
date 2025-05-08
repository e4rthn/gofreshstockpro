# routers/categories.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

# Adjust imports as necessary based on your project structure
import schemas
from services import category_service
from database import get_db

API_INCLUDE_IN_SCHEMA = True

# API Router (Prefix will be added in main.py)
router = APIRouter(
    tags=["API - หมวดหมู่สินค้า"],
    include_in_schema=API_INCLUDE_IN_SCHEMA
)

# --- API Routes Only ---
@router.post("/", response_model=schemas.Category, status_code=status.HTTP_201_CREATED)
async def api_create_new_category(category: schemas.CategoryCreate, db: Session = Depends(get_db)):
    """สร้างหมวดหมู่สินค้าใหม่ (API)"""
    try:
        return category_service.create_category(db=db, category=category)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@router.get("/", response_model=List[schemas.Category])
async def api_read_all_categories(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """ดึงรายการหมวดหมู่สินค้าทั้งหมด (API)"""
    categories_data = category_service.get_categories(db, skip=skip, limit=limit)
    return categories_data.get("items", []) # Return only items for List response

@router.get("/{category_id}", response_model=schemas.Category)
async def api_read_one_category(category_id: int, db: Session = Depends(get_db)):
    """ดึงข้อมูลหมวดหมู่ตามรหัส (API)"""
    db_category = category_service.get_category(db, category_id=category_id)
    if db_category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบหมวดหมู่รหัส {category_id}")
    return db_category

@router.put("/{category_id}", response_model=schemas.Category)
async def api_update_existing_category(category_id: int, category: schemas.CategoryCreate, db: Session = Depends(get_db)):
    """อัปเดตข้อมูลหมวดหมู่ตามรหัส (API)"""
    try:
        updated_category = category_service.update_category(db, category_id=category_id, category_update=category)
        if updated_category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบหมวดหมู่รหัส {category_id}")
        return updated_category
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@router.delete("/{category_id}", response_model=schemas.Category)
async def api_remove_category(category_id: int, db: Session = Depends(get_db)):
    """ลบหมวดหมู่ตามรหัส (API)"""
    try:
        deleted_category = category_service.delete_category(db, category_id=category_id)
        if deleted_category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบหมวดหมู่รหัส {category_id}")
        # The service returns the deleted model, FastAPI serializes it using the response_model
        return deleted_category
    except ValueError as e:
        # Handle dependency error (e.g., products linked)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(f"Unexpected error deleting category {category_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error while deleting category.")

# --- No UI Routes Here Anymore ---