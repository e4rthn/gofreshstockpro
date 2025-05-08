# routers/sales.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

# Adjust imports
import schemas
import models
from services import sales_service # Might need product/location service if API expands
from database import get_db

API_INCLUDE_IN_SCHEMA = True

# API Router (Prefix defined in main.py)
router = APIRouter(
    tags=["API - การขาย (Sales)"],
    include_in_schema=API_INCLUDE_IN_SCHEMA
)

# --- API Routes Only ---
@router.post("/",
             response_model=schemas.Sale, # Should be schemas.Sale for detailed response
             status_code=status.HTTP_201_CREATED)
async def api_record_new_sale(
    sale: schemas.SaleCreate,
    allow_negative_stock: bool = Query(False, alias="allowNegativeStock", description="Allow sale even if stock is insufficient"), # Example Query Param
    db: Session = Depends(get_db)
):
    """ บันทึกข้อมูลการขายใหม่ (API) """
    try:
        # Pass the allow_negative flag to the service
        created_sale = sales_service.record_sale(
            db=db,
            sale_data=sale,
            allow_negative_stock_on_sale=allow_negative_stock
        )
        # The service should return the full Sale object with items loaded
        return created_sale
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบ" in error_message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        elif "สต็อกในระบบไม่เพียงพอ" in error_message or "สต็อกไม่เพียงพอ" in error_message :
            # Provide more context if possible, maybe which item caused it if service returns that info
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        elif "ไม่มีรายการสินค้า" in error_message:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        else:
            print(f"Sale recording ValueError (API): {error_message}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ไม่สามารถบันทึกการขาย: {error_message}")
    except Exception as e:
        print(f"Unexpected Error during sale recording (API): {type(e).__name__} - {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="เกิดข้อผิดพลาดภายในระบบขณะบันทึกการขาย (API)")


@router.get("/report/", response_model=List[schemas.Sale])
async def api_get_sales_report(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, gt=0),
    db: Session = Depends(get_db)
):
    """ ดึงรายงานการขาย (API) """
    try:
        report_data = sales_service.get_sales_report(
            db, start_date=start_date, end_date=end_date, skip=skip, limit=limit
        )
        # Service returns dict {"sales": [...], "total_count": N}
        # API returns just the list of sales
        return report_data.get("sales", [])
    except Exception as e:
        print(f"Error fetching sales report API: {type(e).__name__} - {e}")
        raise HTTPException(status_code=500, detail="Could not fetch sales report data.")


# --- No UI Routes Here Anymore ---