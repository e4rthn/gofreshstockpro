# routers/products.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from urllib.parse import urlencode
import math

# Absolute Imports
import schemas
from services import product_service, category_service
from database import get_db

API_INCLUDE_IN_SCHEMA = True

router = APIRouter(
    tags=["API - สินค้า"],
    include_in_schema=API_INCLUDE_IN_SCHEMA
)

ui_router = APIRouter(
    prefix="/ui/products",
    tags=["หน้าเว็บ - สินค้า"],
    include_in_schema=False
)

# --- API Routes ---
@router.post("/", response_model=schemas.Product, status_code=status.HTTP_201_CREATED)
async def api_create_new_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    try: return product_service.create_product(db=db, product=product)
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบหมวดหมู่" in error_message: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        elif "มีสินค้า SKU" in error_message: raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_message)
        else: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)

@router.get("/", response_model=List[schemas.Product])
async def api_read_all_products(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    products_data = product_service.get_products(db, skip=skip, limit=limit)
    return products_data["items"]

@router.get("/{product_id}", response_model=schemas.Product)
async def api_read_one_product(product_id: int, db: Session = Depends(get_db)):
    db_product = product_service.get_product(db, product_id=product_id)
    if db_product is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสินค้ารหัส {product_id}")
    return db_product

@router.get("/by-category/{category_id}/basic", response_model=List[schemas.ProductBasic])
async def api_get_products_basic_by_category(category_id: int, db: Session = Depends(get_db)):
    products = product_service.get_products_basic_by_category(db, category_id=category_id)
    return products

@router.get("/{product_id}/details", response_model=schemas.Product)
async def api_get_product_details(product_id: int, db: Session = Depends(get_db)):
    db_product = product_service.get_product(db, product_id=product_id)
    if db_product is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสินค้ารหัส {product_id}")
    return db_product

@router.put("/{product_id}", response_model=schemas.Product)
async def api_update_existing_product(product_id: int, product: schemas.ProductCreate, db: Session = Depends(get_db)):
    try:
        updated_product = product_service.update_product(db, product_id=product_id, product_update=product)
        if updated_product is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสินค้ารหัส {product_id}")
        return updated_product
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบหมวดหมู่" in error_message: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        elif "มีสินค้า SKU" in error_message: raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_message)
        else: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)

@router.delete("/{product_id}", response_model=schemas.Product)
async def api_remove_product(product_id: int, db: Session = Depends(get_db)):
    deleted_product_schema = product_service.delete_product(db, product_id=product_id)
    if deleted_product_schema is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสินค้ารหัส {product_id}")
    return deleted_product_schema

# --- UI Routes ---
@ui_router.get("/", response_class=HTMLResponse, name="ui_read_all_products")
async def ui_read_all_products(request: Request, page: int = 1, limit: int = 15, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    skip = (page - 1) * limit;
    if skip < 0: skip = 0
    message = request.query_params.get('message'); error = request.query_params.get('error')
    products_data = product_service.get_products(db=db, skip=skip, limit=limit)
    total_count = products_data["total_count"]; items = products_data["items"]
    total_pages = math.ceil(total_count / limit) if limit > 0 else 0
    return templates.TemplateResponse("products/list.html", {
        "request": request, "products": items, "page": page, "limit": limit,
        "total_count": total_count, "total_pages": total_pages,
        "message": message, "error": error, "skip": skip
    })

@ui_router.get("/add", response_class=HTMLResponse, name="ui_show_add_product_form")
async def ui_show_add_product_form(request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    categories_data = category_service.get_categories(db=db, limit=1000)
    categories = categories_data.get("items", [])
    return templates.TemplateResponse("products/add.html", {"request": request, "categories": categories, "form_data": None, "error": None})

@ui_router.post("/add", response_class=HTMLResponse, name="ui_handle_add_product_form")
async def ui_handle_add_product_form(
    request: Request, db: Session = Depends(get_db), sku: str = Form(...), name: str = Form(...),
    category_id: int = Form(...), price_b2c: float = Form(...),
    standard_cost: Optional[float] = Form(None), price_b2b: Optional[float] = Form(None),
    description: Optional[str] = Form(None), image_url: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = { "sku": sku, "name": name, "category_id": category_id, "price_b2c": price_b2c, "standard_cost": standard_cost, "price_b2b": price_b2b, "description": description, "image_url": image_url }
    try:
        product_data = schemas.ProductCreate(**form_data_dict)
        product_service.create_product(db=db, product=product_data)
        success_message = f"เพิ่มสินค้า '{name}' (SKU: {sku}) เรียบร้อยแล้ว"
        query_params = urlencode({"message": success_message})
        redirect_url = f"{request.app.url_path_for('ui_read_all_products')}?{query_params}"
        return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        categories_data = category_service.get_categories(db=db, limit=1000)
        categories = categories_data.get("items", [])
        return templates.TemplateResponse("products/add.html", {"request": request, "categories": categories, "error": str(e), "form_data": form_data_dict}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         categories_data = category_service.get_categories(db=db, limit=1000)
         categories = categories_data.get("items", [])
         print(f"Unexpected form error: {e}")
         return templates.TemplateResponse("products/add.html", {"request": request, "categories": categories, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะเพิ่มสินค้า", "form_data": form_data_dict }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@ui_router.post("/delete/{product_id}", name="ui_handle_delete_product")
async def ui_handle_delete_product(request: Request, product_id: int, db: Session = Depends(get_db)):
    error_message = None; success_message = None
    try:
        deleted_product_schema = product_service.delete_product(db=db, product_id=product_id)
        if deleted_product_schema is None: error_message = f"ไม่พบสินค้ารหัส {product_id}"
        else: success_message = f"ลบสินค้า '{deleted_product_schema.name}' (รหัส: {product_id}) เรียบร้อยแล้ว"
    except Exception as e:
        print(f"Error deleting product {product_id}: {e}"); error_message = f"เกิดข้อผิดพลาดขณะลบสินค้ารหัส {product_id}: {str(e)}"
    if success_message: query_params = urlencode({"message": success_message})
    elif error_message: query_params = urlencode({"error": error_message})
    else: query_params = urlencode({"error": f"เกิดข้อผิดพลาดบางอย่างขณะลบสินค้ารหัส {product_id}"})
    redirect_url = f"{request.app.url_path_for('ui_read_all_products')}?{query_params}"
    return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)

@ui_router.get("/edit/{product_id}", response_class=HTMLResponse, name="ui_show_edit_product_form")
async def ui_show_edit_product_form(request: Request, product_id: int, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    product_data = product_service.get_product(db, product_id=product_id)
    if product_data is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสินค้ารหัส {product_id}")
    categories_data = category_service.get_categories(db=db, limit=1000)
    categories = categories_data.get("items", [])
    return templates.TemplateResponse("products/edit.html", {"request": request, "product": product_data, "categories": categories, "form_data": None, "error": None})

@ui_router.post("/edit/{product_id}", response_class=HTMLResponse, name="ui_handle_edit_product_form")
async def ui_handle_edit_product_form(
    request: Request, product_id: int, db: Session = Depends(get_db),
    sku: str = Form(...), name: str = Form(...), category_id: int = Form(...),
    price_b2c: float = Form(...), standard_cost: Optional[float] = Form(None),
    price_b2b: Optional[float] = Form(None), description: Optional[str] = Form(None),
    image_url: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = { "sku": sku, "name": name, "category_id": category_id, "price_b2c": price_b2c, "standard_cost": standard_cost, "price_b2b": price_b2b, "description": description, "image_url": image_url }
    try:
        product_update_data = schemas.ProductCreate(**form_data_dict)
        updated_product = product_service.update_product(db, product_id=product_id, product_update=product_update_data)
        if updated_product is None:
             query_params = urlencode({"error": f"ไม่พบสินค้ารหัส {product_id} ที่ต้องการแก้ไข"})
             redirect_url = f"{request.app.url_path_for('ui_read_all_products')}?{query_params}"
             return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)
        success_message = f"อัปเดตข้อมูลสินค้า '{updated_product.name}' (รหัส: {product_id}) เรียบร้อยแล้ว"
        query_params = urlencode({"message": success_message})
        redirect_url = f"{request.app.url_path_for('ui_read_all_products')}?{query_params}"
        return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        product_data = product_service.get_product(db, product_id=product_id)
        categories_data = category_service.get_categories(db=db, limit=1000)
        categories = categories_data.get("items", [])
        if product_data is None :
             return RedirectResponse(url=f"{request.app.url_path_for('ui_read_all_products')}?error=Product+not+found+during+error+handling", status_code=status.HTTP_303_SEE_OTHER)
        return templates.TemplateResponse("products/edit.html", {"request": request, "product": product_data, "categories": categories, "error": str(e), "form_data": form_data_dict }, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         product_data = product_service.get_product(db, product_id=product_id)
         categories_data = category_service.get_categories(db=db, limit=1000)
         categories = categories_data.get("items", [])
         print(f"Unexpected edit form error: {e}")
         context = {"request": request, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะอัปเดตสินค้า", "form_data": form_data_dict }
         if product_data: context["product"] = product_data
         if categories: context["categories"] = categories
         return templates.TemplateResponse("products/edit.html", context, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)