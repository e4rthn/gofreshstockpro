# routers/dashboard.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

# Adjust imports
import schemas
from services import dashboard_service
from database import get_db

API_INCLUDE_IN_SCHEMA = True

# *** ลบ prefix="/api/dashboard" ออกจาก APIRouter ที่นี่ ***
router = APIRouter(
    # prefix="/api/dashboard", # <--- ลบบรรทัดนี้
    tags=["API - Dashboard"],
    responses={404: {"description": "Not found"}},
    include_in_schema=API_INCLUDE_IN_SCHEMA
)

# --- API Routes Only ---
@router.get("/kpis", response_model=schemas.KpiSummarySchema)
async def get_kpi_summary(db: Session = Depends(get_db)):
    """ Get Key Performance Indicators for the dashboard. """
    try:
        kpis = dashboard_service.get_dashboard_kpis(db)
        return kpis
    except Exception as e:
        print(f"Error fetching KPIs API: {type(e).__name__} - {e}")
        raise HTTPException(status_code=500, detail="Could not calculate dashboard KPIs.")

@router.get("/sales-trend-weekly", response_model=List[schemas.SalesTrendItemSchema])
async def get_weekly_sales_trend_api(days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db)):
     """ Get sales trend data for the last N days (default 7). """
     try:
         trend_data = dashboard_service.get_sales_trend(db, days=days)
         return trend_data
     except Exception as e:
         print(f"Error fetching sales trend API: {type(e).__name__} - {e}")
         raise HTTPException(status_code=500, detail="Could not fetch sales trend data.")

@router.get("/top-products-weekly", response_model=List[schemas.ProductPerformanceItemSchema])
async def get_top_products_api(days: int = Query(7, ge=1, le=90), limit: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)):
    """ Get top N selling products by quantity over the last M days. """
    try:
        top_products = dashboard_service.get_top_selling_products(db, days=days, limit=limit)
        return top_products
    except Exception as e:
        print(f"Error fetching top products API: {type(e).__name__} - {e}")
        raise HTTPException(status_code=500, detail="Could not fetch top products data.")

@router.get("/category-distribution", response_model=List[schemas.CategoryDistributionItemSchema])
async def get_category_distribution_api(value_based: bool = Query(False), db: Session = Depends(get_db)):
    """ Get stock distribution by category (count of SKUs or estimated value). """
    try:
        distribution_data = dashboard_service.get_category_stock_distribution(db, value_based=value_based)
        return distribution_data
    except Exception as e:
        print(f"Error fetching category distribution API: {type(e).__name__} - {e}")
        raise HTTPException(status_code=500, detail="Could not fetch category distribution data.")

@router.get("/low-stock-items", response_model=List[schemas.ProductPerformanceItemSchema])
async def get_low_stock_items_api(threshold: int = Query(5, ge=0), limit: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)):
    """ Get N items with stock at or below a threshold. """
    try:
        low_stock = dashboard_service.get_low_stock_items(db, threshold=threshold, limit=limit)
        return low_stock
    except Exception as e:
        print(f"Error fetching low stock items API: {type(e).__name__} - {e}")
        raise HTTPException(status_code=500, detail="Could not fetch low stock items.")

@router.get("/recent-transactions", response_model=List[schemas.RecentTransactionItemSchema])
async def get_recent_transactions_api(limit: int = Query(5, ge=1, le=50), db: Session = Depends(get_db)):
    """ Get N most recent inventory transactions. """
    try:
        transactions = dashboard_service.get_recent_transactions(db, limit=limit)
        return transactions
    except Exception as e:
        print(f"Error fetching recent transactions API: {type(e).__name__} - {e}")
        raise HTTPException(status_code=500, detail="Could not fetch recent transactions.")