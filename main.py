# main.py
import os
from fastapi import FastAPI, Request, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import datetime
from urllib.parse import urlencode as JinjaUrlencode, parse_qs, urlsplit, urlunsplit, quote_plus

# --- Import Routers ---
from routers import (
    categories,
    products,
    locations,
    inventory,
    ui, # General UI (root, dashboard)
    sales,
    stock_count,
    dashboard # Dashboard API
)

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# --- Template Helper (Optional but useful - Kept as is) ---
def generate_filter_url_for_template(request_url_str: str, base_path_for_route: str, **new_params_to_set) -> str:
    _dummy_scheme, _dummy_netloc, _dummy_path, query_string, _dummy_fragment = urlsplit(str(request_url_str))
    current_params_dict = {k: v[0] for k, v in parse_qs(query_string).items()}
    final_query_params = {}
    if 'limit' not in new_params_to_set and 'limit' in current_params_dict: final_query_params['limit'] = current_params_dict['limit']
    elif 'limit' in new_params_to_set and new_params_to_set['limit'] is not None: final_query_params['limit'] = str(new_params_to_set['limit'])
    for key in ['location', 'category', 'days_ahead']: # Added days_ahead for near expiry report
        if key in new_params_to_set:
            value = new_params_to_set[key]
            if value is not None and str(value).strip() != "": final_query_params[key] = str(value)
        elif key in current_params_dict and str(current_params_dict[key]).strip() != "": final_query_params[key] = current_params_dict[key]
    if 'page' in new_params_to_set:
        if new_params_to_set['page'] is not None: final_query_params['page'] = str(new_params_to_set['page'])
    elif any(k in new_params_to_set for k in ['location', 'category', 'days_ahead']): final_query_params['page'] = '1' # Reset if filters change
    elif 'page' in current_params_dict: final_query_params['page'] = current_params_dict['page']
    else: final_query_params['page'] = '1' # Default to page 1 if filters change or no page exists
    query_string_built = JinjaUrlencode(final_query_params)
    return f"{base_path_for_route}?{query_string_built}" if query_string_built else base_path_for_route

# --- FastAPI App Setup ---
templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.globals['current_year'] = datetime.datetime.now().year + 543

app = FastAPI(
    title="GoFresh StockPro",
    description="ระบบจัดการสต็อกสินค้าสำหรับ GoFresh",
    version="1.0.0"
)
app.state.templates = templates
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- Middleware ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    if "X-Frame-Options" in response.headers:
         del response.headers["X-Frame-Options"]
    response.headers["Content-Security-Policy"] = "frame-ancestors 'self';"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
# ------------------------------------

# ========== Include Routers ==========
API_INCLUDE_IN_SCHEMA = True

# --- API Routers ---
app.include_router(categories.router, prefix="/api/categories", tags=["API - หมวดหมู่สินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(locations.router, prefix="/api/locations", tags=["API - สถานที่จัดเก็บ"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(products.router, prefix="/api/products", tags=["API - สินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(inventory.router, prefix="/api/inventory", tags=["API - สต็อกสินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(sales.router, prefix="/api/sales", tags=["API - การขาย (Sales)"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(stock_count.router, prefix="/api/stock-counts", tags=["API - ตรวจนับสต็อก"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["API - Dashboard"], include_in_schema=API_INCLUDE_IN_SCHEMA) # Added prefix for dashboard API

# --- UI Routers (Define Prefixes Consistently Here) ---
app.include_router(ui.router) # Handles root "/" and "/ui/dashboard/"
app.include_router(categories.ui_router, prefix="/ui/categories", tags=["หน้าเว็บ - หมวดหมู่สินค้า"])
app.include_router(products.ui_router, prefix="/ui/products", tags=["หน้าเว็บ - สินค้า"])
app.include_router(locations.ui_router, prefix="/ui/locations", tags=["หน้าเว็บ - สถานที่จัดเก็บ"])
app.include_router(inventory.ui_router, prefix="/ui/inventory", tags=["หน้าเว็บ - สต็อกสินค้า"]) # Contains /summary, /stock-in, /adjust, /transfer, /negative-stock
app.include_router(sales.ui_router, prefix="/ui", tags=["หน้าเว็บ - การขายและรายงาน"]) # Contains /pos, /sales/report
app.include_router(stock_count.ui_router, prefix="/ui/stock-counts", tags=["หน้าเว็บ - ตรวจนับสต็อก"])
# ------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    print("Starting GoFresh StockPro server...")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)