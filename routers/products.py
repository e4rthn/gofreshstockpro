# routers/products.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

# Adjust imports
import schemas
from services import product_service
from database import get_db

API_INCLUDE_IN_SCHEMA = True

# API Router (Prefix defined in main.py)
router = APIRouter(
    tags=["API - สินค้า"],
    include_in_schema=API_INCLUDE_IN_SCHEMA
)

# --- API Routes Only ---
@router.post("/", response_model=schemas.Product, status_code=status.HTTP_201_CREATED)
async def api_create_new_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    try:
        return product_service.create_product(db=db, product_in=product)
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบหมวดหมู่" in error_message: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        elif "มีสินค้า SKU" in error_message or "มีสินค้า Barcode" in error_message:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_message)
        elif "อายุสินค้า (Shelf Life) ต้องไม่ติดลบ" in error_message: # Catch specific validation error
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        else: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
    except Exception as e:
        print(f"Unexpected API Error creating product: {type(e).__name__} - {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while creating the product.")


@router.get("/", response_model=List[schemas.Product])
async def api_read_all_products(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    products_data = product_service.get_products(db, skip=skip, limit=limit)
    return products_data.get("items", [])

@router.get("/{product_id}", response_model=schemas.Product)
async def api_read_one_product(product_id: int, db: Session = Depends(get_db)):
    db_product = product_service.get_product(db, product_id=product_id)
    if db_product is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสินค้ารหัส {product_id}")
    return db_product

@router.get("/by-category/{category_id}/basic", response_model=List[schemas.ProductBasic])
async def api_get_products_basic_by_category(category_id: int, db: Session = Depends(get_db)):
    """ ดึงข้อมูลสินค้าเบื้องต้น (รวม shelf_life_days) ตามหมวดหมู่ """
    try:
        products = product_service.get_products_basic_by_category(db, category_id=category_id)
        return products
    except Exception as e:
        print(f"Unexpected API Error getting basic products by category {category_id}: {type(e).__name__} - {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while fetching basic products.")

@router.get("/lookup-by-scan/{scan_code}", response_model=Optional[schemas.ProductBasic])
async def api_lookup_product_by_scan_code(scan_code: str, db: Session = Depends(get_db)):
    """ ค้นหาสินค้าด้วย SKU หรือ Barcode (สำหรับ POS Scan) """
    if not scan_code or not scan_code.strip():
        return None
    product = product_service.get_product_by_scan_code(db, scan_code=scan_code)
    if not product:
        return None
    # Use model_validate for Pydantic v2
    return schemas.ProductBasic.model_validate(product)

@router.put("/{product_id}", response_model=schemas.Product)
async def api_update_existing_product(product_id: int, product_update_data: schemas.ProductUpdate, db: Session = Depends(get_db)):
    """ อัปเดตข้อมูลสินค้า (รองรับ shelf_life_days) """
    try:
        updated_product = product_service.update_product(db, product_id=product_id, product_update=product_update_data)
        if updated_product is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสินค้ารหัส {product_id}")
        return updated_product
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบหมวดหมู่" in error_message: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        elif "มีสินค้า SKU" in error_message or "มีสินค้า Barcode" in error_message:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_message)
        elif "ต้องไม่ติดลบ" in error_message:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        else: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
    except Exception as e:
        print(f"Unexpected API Error updating product {product_id}: {type(e).__name__} - {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while updating the product.")

@router.delete("/{product_id}", response_model=schemas.Product)
async def api_remove_product(product_id: int, db: Session = Depends(get_db)):
    """ ลบสินค้า """
    try:
        deleted_product_schema = product_service.delete_product(db, product_id=product_id)
        if deleted_product_schema is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสินค้ารหัส {product_id}")
        return deleted_product_schema
    except ValueError as e: # For dependency errors from service
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(f"Unexpected API Error deleting product {product_id}: {type(e).__name__} - {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while deleting the product.")

# --- No UI Routes Here Anymore ---