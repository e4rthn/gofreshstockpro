# routers/ui/products.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from urllib.parse import urlencode
import math

# Adjust imports based on your project structure
import schemas
import models
from services import product_service, category_service
from database import get_db

# Define prefix here
ui_router = APIRouter(
    prefix="/ui/products",
    tags=["UI - สินค้า"],
    include_in_schema=False
)

# --- UI Routes (Moved from original routers/products.py) ---
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
    barcode: Optional[str] = Form(None),
    shelf_life_days: Optional[int] = Form(None), # <-- Included shelf life
    description: Optional[str] = Form(None), image_url: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")
    form_data_dict = {
        "sku": sku, "name": name, "category_id": category_id, "price_b2c": price_b2c,
        "standard_cost": standard_cost, "price_b2b": price_b2b, "barcode": barcode,
        "shelf_life_days": shelf_life_days,
        "description": description, "image_url": image_url
    }
    redirect_url = "/ui/products/" # Fallback
    try:
        payload = {k: v for k, v in form_data_dict.items() if v is not None}
        if shelf_life_days is not None and shelf_life_days < 0:
             raise ValueError("อายุสินค้า (Shelf Life) ต้องไม่ติดลบ")
        if 'barcode' in payload and payload['barcode'] == '':
             payload['barcode'] = None

        product_data = schemas.ProductCreate(**payload)
        product_service.create_product(db=db, product_in=product_data)
        success_message = f"เพิ่มสินค้า '{name}' (SKU: {sku}) เรียบร้อยแล้ว"
        try:
            redirect_url_path = request.app.url_path_for('ui_read_all_products')
            query_params = urlencode({"message": success_message})
            redirect_url = f"{str(redirect_url_path)}?{query_params}"
        except Exception as redirect_err:
             print(f"Error creating redirect URL for product add success: {redirect_err}")
             if success_message: redirect_url += f"?message={success_message}"

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
    redirect_url = "/ui/products/" # Fallback
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
    try:
        redirect_url_path = request.app.url_path_for('ui_read_all_products')
        redirect_url = f"{str(redirect_url_path)}?{query_params}"
    except Exception as redirect_err:
         print(f"Error creating redirect URL for product delete: {redirect_err}")
         if query_params: redirect_url += f"?{query_params}"

    return RedirectResponse(url=str(redirect_url), status_code=status.HTTP_303_SEE_OTHER)


@ui_router.get("/edit/{product_id}", response_class=HTMLResponse, name="ui_show_edit_product_form")
async def ui_show_edit_product_form(request: Request, product_id: int, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")

    product_data = product_service.get_product(db, product_id=product_id)
    if product_data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ไม่พบสินค้ารหัส {product_id}")

    categories_data = category_service.get_categories(db=db, limit=1000)
    categories = categories_data.get("items", [])
    form_data_from_db = schemas.Product.model_validate(product_data).model_dump()
    return templates.TemplateResponse("products/edit.html", {
        "request": request,
        "product": product_data,
        "categories": categories,
        "form_data": form_data_from_db,
        "error": None
        })


@ui_router.post("/edit/{product_id}", response_class=HTMLResponse, name="ui_handle_edit_product_form")
async def ui_handle_edit_product_form(
    request: Request, product_id: int, db: Session = Depends(get_db),
    sku: Optional[str] = Form(None), name: Optional[str] = Form(None),
    category_id: Optional[int] = Form(None), price_b2c: Optional[float] = Form(None),
    standard_cost: Optional[float] = Form(None), price_b2b: Optional[float] = Form(None),
    barcode: Optional[str] = Form(None),
    shelf_life_days: Optional[str] = Form(None), # <-- Receive as string
    description: Optional[str] = Form(None), image_url: Optional[str] = Form(None)
):
    templates = request.app.state.templates
    if templates is None: raise HTTPException(status_code=500, detail="Templates not configured")

    form_data_dict_raw = {
        "sku": sku, "name": name, "category_id": category_id, "price_b2c": price_b2c,
        "standard_cost": standard_cost, "price_b2b": price_b2b, "barcode": barcode,
        "shelf_life_days": shelf_life_days,
        "description": description, "image_url": image_url
    }
    update_payload = {}

    # Add fields only if they are not None initially
    if sku is not None: update_payload['sku'] = sku
    if name is not None: update_payload['name'] = name
    if category_id is not None: update_payload['category_id'] = category_id
    if price_b2c is not None: update_payload['price_b2c'] = price_b2c
    if standard_cost is not None: update_payload['standard_cost'] = standard_cost
    if price_b2b is not None: update_payload['price_b2b'] = price_b2b

    # Handle fields where empty string means clear
    submitted_form_keys = (await request.form()).keys()
    for key in ['barcode', 'description', 'image_url']:
         if key in submitted_form_keys:
             value = form_data_dict_raw.get(key)
             update_payload[key] = None if value == '' else value

    # Handle shelf_life_days specifically
    shelf_life_int: Optional[int] = None
    if 'shelf_life_days' in submitted_form_keys:
        if shelf_life_days == '':
            update_payload['shelf_life_days'] = None # Explicitly set to None if cleared
        else:
            try:
                shelf_life_int = int(shelf_life_days)
                if shelf_life_int < 0:
                    raise ValueError("อายุสินค้า (Shelf Life) ต้องไม่ติดลบ")
                update_payload['shelf_life_days'] = shelf_life_int
            except (ValueError, TypeError):
                 product_data_for_form = product_service.get_product(db, product_id=product_id)
                 categories_data = category_service.get_categories(db=db, limit=1000)
                 categories = categories_data.get("items", [])
                 return templates.TemplateResponse("products/edit.html", {"request": request, "product": product_data_for_form, "categories": categories, "error": "รูปแบบอายุสินค้า (Shelf Life) ไม่ถูกต้อง ต้องเป็นตัวเลขจำนวนเต็ม", "form_data": form_data_dict_raw }, status_code=status.HTTP_400_BAD_REQUEST)
    # If 'shelf_life_days' was not submitted, it won't be in update_payload

    allowed_keys = schemas.ProductUpdate.model_fields.keys()
    update_payload = {k: v for k, v in update_payload.items() if k in allowed_keys}

    redirect_url = "/ui/products/" # Fallback

    try:
        if not update_payload:
             query_params = urlencode({"message": "ไม่มีข้อมูลที่ต้องการอัปเดต"})
             try: redirect_url = request.app.url_path_for('ui_read_all_products') + f"?{query_params}"
             except Exception as e: print(f"Redirect URL Error: {e}"); redirect_url += f"?{query_params}"
             return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

        product_update_schema = schemas.ProductUpdate(**update_payload)
        updated_product = product_service.update_product(db, product_id=product_id, product_update=product_update_schema)

        if updated_product is None:
             error_message = f"ไม่พบสินค้ารหัส {product_id} ที่ต้องการแก้ไข"
             query_params = urlencode({"error": error_message})
             try: redirect_url = request.app.url_path_for('ui_read_all_products') + f"?{query_params}"
             except Exception as e: print(f"Redirect URL Error: {e}"); redirect_url += f"?{query_params}"
             return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

        success_message = f"อัปเดตข้อมูลสินค้า '{updated_product.name}' (รหัส: {product_id}) เรียบร้อยแล้ว"
        query_params = urlencode({"message": success_message})
        try: redirect_url = request.app.url_path_for('ui_read_all_products') + f"?{query_params}"
        except Exception as e: print(f"Redirect URL Error: {e}"); redirect_url += f"?{query_params}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    except ValueError as e:
        product_data_for_form = product_service.get_product(db, product_id=product_id)
        categories_data = category_service.get_categories(db=db, limit=1000)
        categories = categories_data.get("items", [])
        if not product_data_for_form:
            return RedirectResponse(url=request.app.url_path_for('ui_read_all_products') + "?error=Product+not+found+during+edit+error", status_code=status.HTTP_303_SEE_OTHER)
        return templates.TemplateResponse("products/edit.html", {
            "request": request, "product": product_data_for_form, "categories": categories,
            "error": str(e), "form_data": form_data_dict_raw # Use raw dict here
        }, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
         product_data_for_form = product_service.get_product(db, product_id=product_id)
         categories_data = category_service.get_categories(db=db, limit=1000)
         categories = categories_data.get("items", [])
         print(f"Unexpected edit product form error: {type(e).__name__} - {e}")
         context = {
            "request": request, "error": "เกิดข้อผิดพลาดที่ไม่คาดคิดขณะอัปเดตสินค้า",
            "form_data": form_data_dict_raw, # Use raw dict here
             "product": product_data_for_form,
            "categories": categories
         }
         return templates.TemplateResponse("products/edit.html", context, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)