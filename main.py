# main.py
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import datetime

# --- Import SessionMiddleware ---
from starlette.middleware.sessions import SessionMiddleware

# --- Imports for Routers ---
# Use distinct aliases to avoid confusion if module names are the same
from routers import categories as api_categories_router_module
from routers import products as api_products_router_module
from routers import locations as api_locations_router_module
from routers import inventory as api_inventory_router_module # This is for API: routers.inventory
from routers import sales as api_sales_router_module
from routers import stock_count as api_stock_count_router_module
from routers import dashboard as api_dashboard_router_module

try:
    # Suffix UI router module aliases to distinguish them if they have the same name as API counterparts
    from routers.ui import categories as ui_categories_router_module
    from routers.ui import products as ui_products_router_module
    from routers.ui import locations as ui_locations_router_module
    from routers.ui import inventory as ui_inventory_router_module # This is for UI: routers.ui.inventory
    from routers.ui import sales as ui_sales_router_module
    from routers.ui import stock_count as ui_stock_count_router_module
    from routers.ui import dashboard as ui_dashboard_router_module
    print("[*] Successfully imported UI routers from routers.ui")
    ui_routers_imported = True
except ImportError as e:
    print(f"[!!!] Failed to import UI routers from routers.ui: {e}")
    ui_categories_router_module = ui_products_router_module = ui_locations_router_module = \
    ui_inventory_router_module = ui_sales_router_module = ui_stock_count_router_module = \
    ui_dashboard_router_module = None
    ui_routers_imported = False

# --- Import Helper functions from utils.py ---
try:
    from utils import format_thai_datetime, format_thai_date, generate_filter_url_for_template
except ImportError as e:
    print(f"CRITICAL ERROR: Could not import helper functions from utils.py: {e}. App might not work correctly.")
    # Define dummy functions if utils.py is missing, to prevent immediate crash on Jinja setup
    def format_thai_datetime(value, format_str="%d/%m/%Y %H:%M"): return str(value) if value else "-"
    def format_thai_date(value, format_str="%d/%m/%Y"): return str(value) if value else "-"
    def generate_filter_url_for_template(request_url_str: str, base_path_for_route: str, **new_params_to_set) -> str: return base_path_for_route

from zoneinfo import ZoneInfo

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
print(f"[*] Template directory path: {TEMPLATE_DIR}")
print(f"[*] Static directory path: {STATIC_DIR}")

# --- FastAPI App Setup ---
templates = Jinja2Templates(directory=TEMPLATE_DIR)
try:
    templates.env.filters['thaitime'] = format_thai_datetime
    templates.env.filters['thaidate'] = format_thai_date
    print("[*] Custom Jinja filters ('thaitime', 'thaidate') registered successfully.")
    print(f"[DEBUG main.py] Filters loaded after registration: {list(templates.env.filters.keys())}")
except Exception as e:
    print(f"[!!!] Failed to register Jinja filters: {e}")

templates.env.globals['generate_filter_url_for_template_global'] = generate_filter_url_for_template
try:
    thai_tz = ZoneInfo("Asia/Bangkok")
except Exception: # Broad exception for safety
    thai_tz = datetime.timezone.utc
    print("Warning: Asia/Bangkok timezone not found, using UTC for current_year.")
templates.env.globals['current_year'] = datetime.datetime.now(tz=thai_tz).year # Using CE year

app = FastAPI(
    title="GoFresh StockPro - ระบบจัดการสต็อก",
    description="Web application for managing product inventory, sales, and stock counts.",
    version="1.0.0"
)

# --- Add SessionMiddleware ---
# IMPORTANT: Set a strong, random secret key in your environment for production!
# You can generate one using: openssl rand -hex 32
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "your-super-secret-random-string-for-local-dev-sessions-only")
if SESSION_SECRET_KEY == "your-super-secret-random-string-for-local-dev-sessions-only":
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print("WARNING: Using a default SESSION_SECRET_KEY. This is INSECURE for production.")
    print("         Please set a strong, random SESSION_SECRET_KEY environment variable for production.")
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    # session_cookie="gofresh_stockpro_session", # Optional: custom cookie name
    # max_age=14 * 24 * 60 * 60,  # Optional: session lifetime in seconds (e.g., 14 days)
    # https_only=False # Set to True in production if served over HTTPS
)
# --- End SessionMiddleware ---

app.state.templates = templates
try:
    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
        print(f"[*] Successfully mounted static directory: {STATIC_DIR}")
    else:
        print(f"[!] Warning: Static directory not found at {STATIC_DIR}.")
except Exception as e:
    print(f"[!] Error mounting static directory: {e}")

# ========== Include Routers ==========
API_INCLUDE_IN_SCHEMA = True

# --- API Routers ---
# Check if the module was imported successfully before including its router
if api_categories_router_module: app.include_router(api_categories_router_module.router, prefix="/api/categories", tags=["API - หมวดหมู่สินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA)
if api_locations_router_module: app.include_router(api_locations_router_module.router, prefix="/api/locations", tags=["API - สถานที่จัดเก็บ"], include_in_schema=API_INCLUDE_IN_SCHEMA)
if api_products_router_module: app.include_router(api_products_router_module.router, prefix="/api/products", tags=["API - สินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA)
if api_inventory_router_module: app.include_router(api_inventory_router_module.router, prefix="/api/inventory", tags=["API - สต็อกสินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA)
if api_sales_router_module: app.include_router(api_sales_router_module.router, prefix="/api/sales", tags=["API - การขาย (Sales)"], include_in_schema=API_INCLUDE_IN_SCHEMA)
if api_stock_count_router_module: app.include_router(api_stock_count_router_module.router, prefix="/api/stock-counts", tags=["API - ตรวจนับสต็อก"], include_in_schema=API_INCLUDE_IN_SCHEMA)
if api_dashboard_router_module: app.include_router(api_dashboard_router_module.router, prefix="/api/dashboard", tags=["API - Dashboard"], include_in_schema=API_INCLUDE_IN_SCHEMA)

# --- UI Routers ---
if ui_routers_imported: # Check if the main 'routers.ui' import was successful
    if ui_inventory_router_module: app.include_router(ui_inventory_router_module.ui_router)
    if ui_categories_router_module: app.include_router(ui_categories_router_module.ui_router)
    if ui_products_router_module: app.include_router(ui_products_router_module.ui_router)
    if ui_locations_router_module: app.include_router(ui_locations_router_module.ui_router)
    if ui_sales_router_module: app.include_router(ui_sales_router_module.ui_router)
    if ui_stock_count_router_module: app.include_router(ui_stock_count_router_module.ui_router)
    if ui_dashboard_router_module: app.include_router(ui_dashboard_router_module.ui_router)

@app.get("/", response_class=RedirectResponse, include_in_schema=False, tags=["UI - Dashboard & General"])
async def root_redirect(request: Request):
    dashboard_url = "/ui/dashboard/" # Default fallback
    try:
        # Ensure 'ui_dashboard' is the correct 'name' of the route in your ui_dashboard_router_module
        if ui_dashboard_router_module: # Check if the UI dashboard router module was imported
             dashboard_url = str(request.app.url_path_for("ui_dashboard"))
    except Exception as e:
        print(f"Error finding 'ui_dashboard' for root redirect in main.py: {e}. Falling back to {dashboard_url}.")
    return RedirectResponse(url=dashboard_url)

@app.get("/health", tags=["Health Check"], include_in_schema=False)
async def health_check():
    return {"status": "ok"}

print("[*] Application setup complete. Routers included.")