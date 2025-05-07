# routers/products.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from urllib.parse import urlencode
import math

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
    try:
        return product_service.create_product(db=db, product_in=product)
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบหมวดหมู่" in error_message: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        elif "มีสินค้า SKU" in error_message or "มีสินค้า Barcode" in error_message:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_message)
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
    try:
        print(f"API: Fetching basic products for category {category_id}")
        products = product_service.get_products_basic_by_category(db, category_id=category_id)
        print(f"API: Service returned {len(products)} products.")
        # Always return 200 OK with the list (empty or not)
        return products
    except ValueError as e:
        # This should ideally not be raised anymore if service returns [] for not found category
        print(f"API: ValueError fetching basic products for category {category_id}: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        print(f"Unexpected API Error getting basic products by category {category_id}: {type(e).__name__} - {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.get("/lookup-by-scan/{scan_code}", response_model=Optional[schemas.ProductBasic])
async def api_lookup_product_by_scan_code(scan_code: str, db: Session = Depends(get_db)):
    if not scan_code or not scan_code.strip():
        return None # Or raise HTTPException for bad request
    product = product_service.get_product_by_scan_code(db, scan_code=scan_code)
    if not product:
        return None # Will be serialized as null
    # Ensure ProductBasic has all necessary fields (id, name, sku, barcode, price_b2c)
    return product # FastAPI will convert using ProductBasic schema due to response_model

@router.put("/{product_id}", response_model=schemas.Product)
async def api_update_existing_product(product_id: int, product_update_data: schemas.ProductUpdate, db: Session = Depends(get_db)): # Use ProductUpdate
    try:
        updated_product = product_service.update_product(db, product_id=product_id, product_update=product_update_data)
        if updated_product is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสินค้ารหัส {product_id}")
        return updated_product
    except ValueError as e:
        error_message = str(e)
        if "ไม่พบหมวดหมู่" in error_message: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        elif "มีสินค้า SKU" in error_message or "มีสินค้า Barcode" in error_message:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_message)
        else: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)

@router.delete("/{product_id}", response_model=schemas.Product)
async def api_remove_product(product_id: int, db: Session = Depends(get_db)):
    try:
        deleted_product_schema = product_service.delete_product(db, product_id=product_id)
        if deleted_product_schema is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสินค้ารหัส {product_id}")
        return deleted_product_schema
    except ValueError as e: # For dependency errors from service
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# --- UI Routes ---
@ui_router.get("/", response_class=HTMLResponse, name="ui_read_all_products")
async def ui_read_all_products(request: Request, page: int = 1, limit: int = 15, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    skip = (page - 1) * limit
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
    barcode: Optional[str] = Form(None), # Added barcode
    description: Optional[str] = Form(None), image_url: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = {
        "sku": sku, "name": name, "category_id": category_id, "price_b2c": price_b2c,
        "standard_cost": standard_cost, "price_b2b": price_b2b, "barcode": barcode,
        "description": description, "image_url": image_url
    }
    try:
        product_data = schemas.ProductCreate(**form_data_dict)
        product_service.create_product(db=db, product_in=product_data)
        success_message = f"เพิ่มสินค้า '{name}' (SKU: {sku}) เรียบร้อยแล้ว"
        query_params = urlencode({"message": success_message})
        redirect_url_path = request.app.url_path_for('ui_read_all_products')
        redirect_url = f"{str(redirect_url_path)}?{query_params}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        categories_data = category_service.get_categories(db=db, limit=1000)
        categories = categories_data.get("items", [])
        return templates.TemplateResponse("products/add.html", {"request": request, "categories": categories, "error": str(e), "form_data": form_data_dict}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         categories_data = category_service.get_categories(db=db, limit=1000)
         categories = categories_data.get("items", [])
         print(f"Unexpected add product form error: {type(e).__name__} - {e}")
         return templates.TemplateResponse("products/add.html", {"request": request, "categories": categories, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะเพิ่มสินค้า", "form_data": form_data_dict }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@ui_router.post("/delete/{product_id}", name="ui_handle_delete_product")
async def ui_handle_delete_product(request: Request, product_id: int, db: Session = Depends(get_db)):
    error_message = None; success_message = None
    try:
        deleted_product_schema = product_service.delete_product(db=db, product_id=product_id)
        if deleted_product_schema is None:
            error_message = f"ไม่พบสินค้ารหัส {product_id}"
        else:
            success_message = f"ลบสินค้า '{deleted_product_schema.name}' (รหัส: {product_id}) เรียบร้อยแล้ว"
    except ValueError as e: # Catch dependency error from service
        error_message = str(e)
    except Exception as e:
        print(f"Error deleting product {product_id}: {type(e).__name__} - {e}")
        error_message = f"เกิดข้อผิดพลาดขณะลบสินค้ารหัส {product_id}"

    query_params_dict = {}
    if success_message: query_params_dict["message"] = success_message
    elif error_message: query_params_dict["error"] = error_message
    else: query_params_dict["error"] = f"เกิดข้อผิดพลาดบางอย่างขณะลบสินค้ารหัส {product_id}"
    
    query_params = urlencode(query_params_dict)
    redirect_url_path = request.app.url_path_for('ui_read_all_products')
    redirect_url = f"{str(redirect_url_path)}?{query_params}"
    return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)


@ui_router.get("/edit/{product_id}", response_class=HTMLResponse, name="ui_show_edit_product_form")
async def ui_show_edit_product_form(request: Request, product_id: int, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")

    # --- จุดที่ตรวจสอบ ---
    product_data = product_service.get_product(db, product_id=product_id)
    if product_data is None:
        # ถ้าไม่พบสินค้า ให้ Raise 404
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสินค้ารหัส {product_id}")
    # --------------------

    categories_data = category_service.get_categories(db=db, limit=1000)
    categories = categories_data.get("items", [])
    return templates.TemplateResponse("products/edit.html", {
        "request": request,
        "product": product_data,
        "categories": categories,
        "form_data": schemas.Product.model_validate(product_data).model_dump(), # Send current data
        "error": None
        })

@ui_router.post("/edit/{product_id}", response_class=HTMLResponse, name="ui_handle_edit_product_form")
async def ui_handle_edit_product_form(
    request: Request, product_id: int, db: Session = Depends(get_db),
    sku: Optional[str] = Form(None), name: Optional[str] = Form(None), # Make fields optional for partial update
    category_id: Optional[int] = Form(None), price_b2c: Optional[float] = Form(None),
    standard_cost: Optional[float] = Form(None), price_b2b: Optional[float] = Form(None),
    barcode: Optional[str] = Form(None), # Added barcode
    description: Optional[str] = Form(None), image_url: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")

    form_data_dict = {
        "sku": sku, "name": name, "category_id": category_id, "price_b2c": price_b2c,
        "standard_cost": standard_cost, "price_b2b": price_b2b, "barcode": barcode,
        "description": description, "image_url": image_url
    }
    # Filter out None values to only pass fields that were actually submitted or intended for update
    # This is important for schemas.ProductUpdate(exclude_unset=True) to work as expected
    update_payload = {k: v for k, v in form_data_dict.items() if v is not None or k in ['barcode', 'description', 'image_url', 'standard_cost', 'price_b2b']}
    # For fields like barcode, description, image_url, an empty string from form might mean "clear this field"
    # Handle this logic in Pydantic schema or service layer if "" should mean None.
    # Current ProductBase validator for barcode handles "" -> None.

    try:
        # Use ProductUpdate schema for partial updates
        product_update_schema = schemas.ProductUpdate(**update_payload)
        updated_product = product_service.update_product(db, product_id=product_id, product_update=product_update_schema)

        if updated_product is None: # Should be caught by service if product_id is invalid
             error_message = f"ไม่พบสินค้ารหัส {product_id} ที่ต้องการแก้ไข"
             query_params = urlencode({"error": error_message})
             redirect_url_path = request.app.url_path_for('ui_read_all_products')
             return RedirectResponse(url=f"{str(redirect_url_path)}?{query_params}", status_code=status.HTTP_303_SEE_OTHER)

        success_message = f"อัปเดตข้อมูลสินค้า '{updated_product.name}' (รหัส: {product_id}) เรียบร้อยแล้ว"
        query_params = urlencode({"message": success_message})
        redirect_url_path = request.app.url_path_for('ui_read_all_products')
        return RedirectResponse(url=f"{str(redirect_url_path)}?{query_params}", status_code=status.HTTP_303_SEE_OTHER)

    except ValueError as e: # From service layer
        product_data_for_form = product_service.get_product(db, product_id=product_id)
        categories_data = category_service.get_categories(db=db, limit=1000)
        categories = categories_data.get("items", [])
        if not product_data_for_form: # Should not happen if GET was successful
            # Redirect or show generic error
            return RedirectResponse(url=request.app.url_path_for('ui_read_all_products') + "?error=Product+not+found+during+edit+error", status_code=status.HTTP_303_SEE_OTHER)
        return templates.TemplateResponse("products/edit.html", {
            "request": request, "product": product_data_for_form, "categories": categories,
            "error": str(e), "form_data": form_data_dict # Pass back the submitted data
        }, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         product_data_for_form = product_service.get_product(db, product_id=product_id)
         categories_data = category_service.get_categories(db=db, limit=1000)
         categories = categories_data.get("items", [])
         print(f"Unexpected edit product form error: {type(e).__name__} - {e}")
         context = {
            "request": request, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะอัปเดตสินค้า",
            "form_data": form_data_dict, "product": product_data_for_form, "categories": categories
         }
         return templates.TemplateResponse("products/edit.html", context, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)