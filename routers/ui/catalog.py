# routers/ui/catalog.py
from fastapi import APIRouter, Depends, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, joinedload
from typing import Optional, List

import models
from services import product_service, category_service
from database import get_db

ui_router = APIRouter(
    prefix="/ui/catalog",
    tags=["UI - แคตตาล็อกราคา"],
    include_in_schema=False
)

@ui_router.get("/price-display/", response_class=HTMLResponse, name="ui_price_display")
async def show_price_display_page(
    request: Request,
    db: Session = Depends(get_db),
    # --- เปลี่ยน type hint ตรงนี้ ---
    category_query_param: Optional[str] = Query(None, alias="category"), # รับเป็น string ก่อน
    # -----------------------------
    search_query: Optional[str] = Query(None, alias="search")
):
    templates = request.app.state.templates
    if templates is None:
        raise HTTPException(status_code=500, detail="Templates not configured")

    # --- แปลง category_query_param เป็น int ถ้ามีค่าและเป็นตัวเลข ---
    category_filter: Optional[int] = None
    if category_query_param and category_query_param.strip().isdigit():
        category_filter = int(category_query_param.strip())
    # ---------------------------------------------------------

    products_query = db.query(models.Product).options(
        joinedload(models.Product.category)
    )

    if category_filter is not None: # ใช้ category_filter ที่แปลงแล้ว
        products_query = products_query.filter(models.Product.category_id == category_filter)

    if search_query and search_query.strip():
        search_term_like = f"%{search_query.strip()}%"
        products_query = products_query.filter(
            (models.Product.name.ilike(search_term_like)) |
            (models.Product.sku.ilike(search_term_like))
        )
    
    all_products = products_query.order_by(models.Product.name).all()

    categories_data = category_service.get_categories(db=db, limit=1000)
    all_categories = categories_data.get("items", [])

    context = {
        "request": request,
        "products": all_products,
        "all_categories": all_categories,
        "selected_category_id": category_filter, # ส่งค่าที่แปลงแล้วไป template
        "search_term": search_query,
        "message": request.query_params.get('message'),
        "error": request.query_params.get('error'),
    }
    return templates.TemplateResponse("catalog/price_display.html", context)