# main.py
import os
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import datetime
from urllib.parse import urlencode as JinjaUrlencode, parse_qs, urlsplit, urlunsplit, quote_plus

# --- Import Routers ---
from routers import categories, products, locations, inventory, ui, sales, stock_count, dashboard

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# --- Template Helper (Optional but useful) ---
def generate_filter_url_for_template(request_url_str: str, base_path_for_route: str, **new_params_to_set) -> str:
    _dummy_scheme, _dummy_netloc, _dummy_path, query_string, _dummy_fragment = urlsplit(str(request_url_str))
    current_params_dict = {k: v[0] for k, v in parse_qs(query_string).items()}
    final_query_params = {}
    if 'limit' not in new_params_to_set and 'limit' in current_params_dict: final_query_params['limit'] = current_params_dict['limit']
    elif 'limit' in new_params_to_set and new_params_to_set['limit'] is not None: final_query_params['limit'] = str(new_params_to_set['limit'])
    for key in ['location', 'category']:
        if key in new_params_to_set:
            value = new_params_to_set[key]
            if value is not None and str(value).strip() != "": final_query_params[key] = str(value)
        elif key in current_params_dict and str(current_params_dict[key]).strip() != "": final_query_params[key] = current_params_dict[key]
    if 'page' in new_params_to_set:
        if new_params_to_set['page'] is not None: final_query_params['page'] = str(new_params_to_set['page'])
    elif any(k in new_params_to_set for k in ['location', 'category']): final_query_params['page'] = '1'
    elif 'page' in current_params_dict: final_query_params['page'] = current_params_dict['page']
    else: final_query_params['page'] = '1'
    query_string_built = JinjaUrlencode(final_query_params)
    return f"{base_path_for_route}?{query_string_built}" if query_string_built else base_path_for_route

# --- FastAPI App Setup ---
templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.globals['generate_filter_url_for_template_global'] = generate_filter_url_for_template
templates.env.globals['current_year'] = datetime.datetime.utcnow().year + 543

app = FastAPI(title="GoFresh StockPro - ระบบจัดการสต็อก")
app.state.templates = templates
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ========== Include Routers ==========
API_INCLUDE_IN_SCHEMA = True
app.include_router(categories.router, prefix="/api/categories", tags=["API - หมวดหมู่สินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA)
# !!! ลบบรรทัดนี้ออก: app.include_router(products.ui_router, tags=["API - หมวดหมู่สินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA) !!!
app.include_router(locations.router, prefix="/api/locations", tags=["API - สถานที่จัดเก็บ"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(products.router, prefix="/api/products", tags=["API - สินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA) # <-- API router ของ products อยู่ตรงนี้
app.include_router(inventory.router, prefix="/api/inventory", tags=["API - สต็อกสินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(sales.router, prefix="/api/sales", tags=["API - การขาย (Sales)"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(stock_count.router, prefix="/api/stock-counts", tags=["API - ตรวจนับสต็อก"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(dashboard.router) # API Router for Dashboard (prefix="/api/dashboard")

# --- UI Routers ---
app.include_router(ui.router) # Includes "/" and "/ui/dashboard/" routes
app.include_router(categories.ui_router, prefix="/ui/categories")
app.include_router(products.ui_router)   # <-- Include UI Router ของ products ที่นี่ (ไม่ต้องมี prefix เพราะกำหนดใน router แล้ว)
app.include_router(locations.ui_router, prefix="/ui/locations")
app.include_router(inventory.ui_router) # Prefix="/ui/inventory" defined inside router
app.include_router(sales.ui_router, prefix="/ui") # Prefix="/ui", contains /pos, /sales/report
app.include_router(stock_count.ui_router, prefix="/ui/stock-counts")