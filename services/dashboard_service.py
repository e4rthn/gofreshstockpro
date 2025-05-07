# services/dashboard_service.py
from sqlalchemy.orm import Session, joinedload, subqueryload
from sqlalchemy import func, distinct, desc, cast, Date as SQLDate
from datetime import date, timedelta, datetime, time
from typing import List, Dict, Any, Optional

# Import necessary models directly and schemas
from models import (
    Sale, SaleItem, CurrentStock, InventoryTransaction, TransactionType,
    Product, Category, Location
)
import schemas

def get_dashboard_kpis(db: Session, near_expiry_days: int = 7) -> schemas.KpiSummarySchema:
    """ Calculates Key Performance Indicators for the dashboard. """
    today_start = datetime.combine(date.today(), time.min)
    today_end = datetime.combine(date.today() + timedelta(days=1), time.min)
    today_date_only = date.today()
    near_expiry_threshold_date = today_date_only + timedelta(days=near_expiry_days)

    sales_today_agg = None
    negative_stock_count = 0
    near_expiry_count_final = 0

    try:
        # --- Today's Sales ---
        sales_today_agg = db.query(
            func.coalesce(func.sum(Sale.total_amount), 0.0).label('total_sales'),
            func.count(Sale.id).label('sales_count')
        ).filter(
            Sale.sale_date >= today_start,
            Sale.sale_date < today_end
        ).one()

        # --- Negative Stock Count ---
        negative_stock_count = db.query(func.count(CurrentStock.id)).filter(
            CurrentStock.quantity < 0
        ).scalar() or 0

        # --- Near Expiry Count ---
        near_expiry_product_ids_subquery = db.query(
            distinct(InventoryTransaction.product_id).label("product_id")
        ).filter(
            InventoryTransaction.transaction_type == TransactionType.STOCK_IN,
            InventoryTransaction.expiry_date.isnot(None),
            InventoryTransaction.expiry_date >= today_date_only,
            InventoryTransaction.expiry_date <= near_expiry_threshold_date
        ).subquery('near_expiry_pids')

        near_expiry_count_final = db.query(func.count(distinct(CurrentStock.product_id))).join(
             near_expiry_product_ids_subquery,
             CurrentStock.product_id == near_expiry_product_ids_subquery.c.product_id
        ).filter(CurrentStock.quantity > 0).scalar() or 0

    except Exception as e:
        print(f"!!! Error calculating KPIs in dashboard_service.py: {type(e).__name__} - {e}")
        import traceback
        traceback.print_exc()
        # Return default values in case of error to avoid breaking the API entirely
        return schemas.KpiSummarySchema()

    return schemas.KpiSummarySchema(
        today_sales_total=float(sales_today_agg.total_sales if sales_today_agg else 0.0),
        today_sales_count=int(sales_today_agg.sales_count if sales_today_agg else 0),
        negative_stock_item_count=int(negative_stock_count),
        near_expiry_item_count=int(near_expiry_count_final)
    )

# ... (rest of the functions: get_sales_trend, get_top_selling_products, etc. as provided previously) ...
def get_sales_trend(db: Session, days: int = 7) -> List[schemas.SalesTrendItemSchema]:
    """ Gets total sales for each of the last 'days', filling missing days with 0. """
    trend_result: List[schemas.SalesTrendItemSchema] = []
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1) # Inclusive start date
        all_dates = [start_date + timedelta(days=i) for i in range(days)]
        start_datetime = datetime.combine(start_date, time.min)
        end_datetime = datetime.combine(end_date + timedelta(days=1), time.min)

        sales_data = db.query(
            cast(Sale.sale_date, SQLDate).label("sale_day"), # Cast timestamp to date
            func.sum(Sale.total_amount).label("daily_total")
        ).filter(
            Sale.sale_date >= start_datetime,
            Sale.sale_date < end_datetime
        ).group_by(
            cast(Sale.sale_date, SQLDate)
        ).order_by(
            cast(Sale.sale_date, SQLDate)
        ).all()

        sales_dict = {item.sale_day: item.daily_total for item in sales_data}

        for current_date in all_dates:
            total = sales_dict.get(current_date, 0.0)
            trend_result.append(schemas.SalesTrendItemSchema(date=current_date, total_sales=float(total or 0.0)))

    except Exception as e:
        print(f"!!! Error calculating sales trend: {type(e).__name__} - {e}")
        # Return empty list on error or re-raise
    return trend_result

def get_top_selling_products(db: Session, days: int = 7, limit: int = 5) -> List[schemas.ProductPerformanceItemSchema]:
    """ Gets top N selling products by quantity over the last 'days'. """
    result_list: List[schemas.ProductPerformanceItemSchema] = []
    try:
        end_date = date.today() + timedelta(days=1)
        start_date = end_date - timedelta(days=days)
        start_datetime = datetime.combine(start_date, time.min)
        end_datetime = datetime.combine(end_date, time.min)

        top_products_query = db.query(
            SaleItem.product_id,
            Product.name.label("product_name"),
            Product.sku.label("product_sku"),
            func.sum(SaleItem.quantity).label("total_quantity")
        ).join(
            Sale, SaleItem.sale_id == Sale.id
        ).join(
            Product, SaleItem.product_id == Product.id
        ).filter(
            Sale.sale_date >= start_datetime,
            Sale.sale_date < end_datetime
        ).group_by(
            SaleItem.product_id, Product.name, Product.sku
        ).order_by(
            desc("total_quantity")
        ).limit(limit).all()

        result_list = [
            schemas.ProductPerformanceItemSchema(
                product_id=p.product_id,
                product_name=p.product_name,
                product_sku=p.product_sku,
                value=float(p.total_quantity or 0) # value is quantity here
            ) for p in top_products_query
        ]
    except Exception as e:
         print(f"!!! Error calculating top selling products: {type(e).__name__} - {e}")
         # Return empty list on error or re-raise
    return result_list

def get_category_stock_distribution(db: Session, value_based: bool = False) -> List[schemas.CategoryDistributionItemSchema]:
    """ Calculates stock distribution by category (either by item count or estimated value). """
    result_list: List[schemas.CategoryDistributionItemSchema] = []
    try:
        if value_based:
            distribution_query = db.query(
                Category.id.label("category_id"),
                Category.name.label("category_name"),
                func.sum(func.coalesce(CurrentStock.quantity, 0) * func.coalesce(Product.standard_cost, 0)).label("total_value")
            ).select_from(Category).outerjoin(
                Product, Category.id == Product.category_id
            ).outerjoin(
                CurrentStock, Product.id == CurrentStock.product_id
            ).group_by(Category.id, Category.name).order_by(desc("total_value")).all()
        else:
            distribution_query = db.query(
                Category.id.label("category_id"),
                Category.name.label("category_name"),
                func.count(distinct(CurrentStock.product_id)).label("total_value")
            ).select_from(Category).outerjoin(
                Product, Category.id == Product.category_id
            ).outerjoin(
                CurrentStock, Product.id == CurrentStock.product_id
            ).filter(
                CurrentStock.quantity > 0
            ).group_by(Category.id, Category.name).order_by(desc("total_value")).all()

        result_list = [
            schemas.CategoryDistributionItemSchema(
                category_id=c.category_id,
                category_name=c.category_name,
                value=float(c.total_value or 0)
            )
            for c in distribution_query if c.total_value and c.total_value > 0
        ]
    except Exception as e:
         print(f"!!! Error calculating category distribution: {type(e).__name__} - {e}")
         # Return empty list on error or re-raise
    return result_list


def get_low_stock_items(db: Session, threshold: int = 5, limit: int = 5) -> List[schemas.ProductPerformanceItemSchema]:
     """ Gets N items with stock quantity at or below the threshold (non-negative). """
     result_list: List[schemas.ProductPerformanceItemSchema] = []
     try:
         low_stock_items_query = db.query(
             CurrentStock.product_id,
             Product.name.label("product_name"),
             Product.sku.label("product_sku"),
             CurrentStock.quantity.label("current_quantity")
         ).join(
             Product, CurrentStock.product_id == Product.id
         ).filter(
             CurrentStock.quantity >= 0,
             CurrentStock.quantity <= threshold
         ).order_by(
             CurrentStock.quantity.asc()
         ).limit(limit).all()

         result_list = [
             schemas.ProductPerformanceItemSchema(
                 product_id=p.product_id,
                 product_name=p.product_name,
                 product_sku=p.product_sku,
                 value=float(p.current_quantity)
             ) for p in low_stock_items_query
         ]
     except Exception as e:
         print(f"!!! Error calculating low stock items: {type(e).__name__} - {e}")
         # Return empty list on error or re-raise
     return result_list

def get_recent_transactions(db: Session, limit: int = 5) -> List[schemas.RecentTransactionItemSchema]:
    """ Gets the N most recent inventory transactions with related info. """
    result_list: List[schemas.RecentTransactionItemSchema] = []
    try:
        recent_tx_query = db.query(InventoryTransaction).options(
            joinedload(InventoryTransaction.product),
            joinedload(InventoryTransaction.location)
        ).order_by(InventoryTransaction.transaction_date.desc()).limit(limit).all()

        result_list = [
            schemas.RecentTransactionItemSchema(
                id=tx.id,
                transaction_date=tx.transaction_date,
                transaction_type=tx.transaction_type.name,
                product_name=tx.product.name if tx.product else "N/A",
                location_name=tx.location.name if tx.location else "N/A",
                quantity_change=tx.quantity_change,
                notes=tx.notes
            )
            for tx in recent_tx_query
        ]
    except Exception as e:
        print(f"!!! Error calculating recent transactions: {type(e).__name__} - {e}")
        # Return empty list on error or re-raise
    return result_list