# main.py
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import datetime
from urllib.parse import urlencode as JinjaUrlencode, parse_qs, urlsplit, urlunsplit, quote_plus

# --- Imports for Routers (Refactored Structure) ---
from routers import (
    categories as api_categories, products as api_products, locations as api_locations,
    inventory as api_inventory, sales as api_sales, stock_count as api_stock_count,
    dashboard as api_dashboard
)
try:
    from routers.ui import (
        categories as ui_categories, products as ui_products, locations as ui_locations,
        inventory as ui_inventory, sales as ui_sales, stock_count as ui_stock_count,
        dashboard as ui_dashboard
    )
    print("[*] Successfully imported UI routers from routers.ui")
    ui_routers_imported = True
except ImportError as e:
    print(f"[!!!] Failed to import UI routers from routers.ui: {e}")
    ui_categories = ui_products = ui_locations = ui_inventory = ui_sales = ui_stock_count = ui_dashboard = None
    ui_routers_imported = False

from fastapi.routing import APIRoute

# *** เพิ่ม Imports สำหรับ Timezone ***
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Optional, Union
# **********************************

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
print(f"[*] Template directory path: {TEMPLATE_DIR}")
print(f"[*] Static directory path: {STATIC_DIR}")

# --- Template Helper ---
def generate_filter_url_for_template(request_url_str: str, base_path_for_route: str, **new_params_to_set) -> str:
    # ... (implementation) ...
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
    separator = "?" if query_string_built else ""
    return f"{base_path_for_route.rstrip('/')}{separator}{query_string_built}"


# *** ฟังก์ชันสำหรับแปลงเวลาไทย ***
def format_thai_datetime(value: Optional[Union[datetime.datetime, datetime.date]], format: str = "%d/%m/%Y %H:%M") -> str: # <-- เปลี่ยน Default Format
    """Jinja2 filter to convert UTC or naive datetime to Thai time and format it."""
    if value is None: return "-"
    try: thai_tz = ZoneInfo("Asia/Bangkok")
    except ZoneInfoNotFoundError:
        print("!!! Timezone 'Asia/Bangkok' not found. Using UTC fallback. Install tzdata? (pip install tzdata)")
        try: return value.strftime(format)
        except: return str(value)

    if isinstance(value, datetime.datetime):
        if value.tzinfo is None: value = value.replace(tzinfo=ZoneInfo("UTC"))
        return value.astimezone(thai_tz).strftime(format)
    elif isinstance(value, datetime.date):
         date_format = "%d/%m/%Y" # Default date format (Thai style)
         if any(c in format for c in ['H', 'I', 'M', 'S', 'p', 'z', 'Z']):
              print(f"Warning: Time format '{format}' provided for date object '{value}'. Using date format '%d/%m/%Y'.")
         else: date_format = format # Use provided format if it's date-only
         return value.strftime(date_format)
    return str(value)

def format_thai_date(value: Optional[Union[datetime.datetime, datetime.date]], format: str = "%d/%m/%Y") -> str: # <-- เปลี่ยน Default Format
     """Jinja2 filter to format date as Thai date."""
     if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
          if any(c in format for c in ['H', 'I', 'M', 'S', 'p', 'z', 'Z']): format = "%d/%m/%Y"
     return format_thai_datetime(value, format=format)
# **********************************

# --- FastAPI App Setup ---
templates = Jinja2Templates(directory=TEMPLATE_DIR)
# *** ลงทะเบียน Custom Filter ***
try:
    templates.env.filters['thaitime'] = format_thai_datetime
    templates.env.filters['thaidate'] = format_thai_date
    print("[*] Custom Jinja filters ('thaitime', 'thaidate') registered successfully.")
    # *** เพิ่ม Print Statement ***
    print(f"[DEBUG main.py] Filters loaded after registration: {list(templates.env.filters.keys())}")
    # **************************
except Exception as e:
    print(f"[!!!] Failed to register Jinja filters: {e}")
# ******************************
templates.env.globals['generate_filter_url_for_template_global'] = generate_filter_url_for_template
try: thai_tz = ZoneInfo("Asia/Bangkok")
except: thai_tz = datetime.timezone.utc
templates.env.globals['current_year'] = datetime.datetime.now(tz=thai_tz).year + 543

app = FastAPI(
    title="GoFresh StockPro - ระบบจัดการสต็อก",
    description="Web application for managing product inventory, sales, and stock counts.",
    version="1.0.0"
)
app.state.templates = templates # Share the *configured* templates instance
try:
    if os.path.isdir(STATIC_DIR): app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static"); print(f"[*] Successfully mounted static directory: {STATIC_DIR}")
    else: print(f"[!] Warning: Static directory not found at {STATIC_DIR}.")
except Exception as e: print(f"[!] Error mounting static directory: {e}")

# ========== Include Routers (ใช้โครงสร้างใหม่) ==========

# --- API Routers ---
API_INCLUDE_IN_SCHEMA = True
# *** กำหนด prefix ที่นี่ สำหรับ API routers ***
app.include_router(api_categories.router, prefix="/api/categories", tags=["API - หมวดหมู่สินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(api_locations.router, prefix="/api/locations", tags=["API - สถานที่จัดเก็บ"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(api_products.router, prefix="/api/products", tags=["API - สินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(api_inventory.router, prefix="/api/inventory", tags=["API - สต็อกสินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(api_sales.router, prefix="/api/sales", tags=["API - การขาย (Sales)"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(api_stock_count.router, prefix="/api/stock-counts", tags=["API - ตรวจนับสต็อก"], include_in_schema=API_INCLUDE_IN_SCHEMA)
# *** กำหนด prefix ที่นี่ สำหรับ API Dashboard ***
app.include_router(api_dashboard.router, prefix="/api/dashboard", tags=["API - Dashboard"], include_in_schema=API_INCLUDE_IN_SCHEMA)

# --- UI Routers (ใช้ router จาก routers.ui) ---
# Include โดย *ไม่ต้องใส่* prefix ที่นี่ (เพราะ prefix กำหนดในไฟล์ router แต่ละตัวแล้ว)
# ตรวจสอบว่า import สำเร็จก่อน include
if ui_inventory: app.include_router(ui_inventory.ui_router)
if ui_categories: app.include_router(ui_categories.ui_router)
if ui_products: app.include_router(ui_products.ui_router)
if ui_locations: app.include_router(ui_locations.ui_router)
if ui_sales: app.include_router(ui_sales.ui_router)
if ui_stock_count: app.include_router(ui_stock_count.ui_router)
# Include UI Dashboard (prefix "/ui" ถูกกำหนดใน routers/ui/dashboard.py แล้ว)
if ui_dashboard: app.include_router(ui_dashboard.ui_router)
# *********************************************************

# --- Root Redirect ---
# Route นี้จะถูกจัดการโดย ui_dashboard.ui_router ถ้า include โดยไม่มี prefix
# หรือเราสามารถกำหนดที่นี่ได้เลย
@app.get("/", response_class=RedirectResponse, include_in_schema=False, tags=["UI - Dashboard & General"])
async def root_redirect(request: Request):
    """ Redirects root path to the main UI dashboard """
    dashboard_url = "/ui/dashboard/" # กำหนด path ตรงๆ เลยเพื่อความแน่นอน
    # ลองหา path แบบ dynamic ดูก่อน ถ้าไม่ได้ก็ใช้ค่า default
    # try:
    #     # Ensure ui_dashboard route name exists in the included ui_dashboard.ui_router
    #     dashboard_url = request.app.url_path_for("ui_dashboard")
    # except Exception as e:
    #     print(f"Error finding 'ui_dashboard' for root redirect in main.py: {e}. Falling back.")
    return RedirectResponse(url=dashboard_url)
# --------------------

# --- Debug Route ---
@app.get("/debug-routes", include_in_schema=False, response_class=JSONResponse)
async def get_all_routes(request: Request):
    """ แสดงรายการ routes ทั้งหมดที่ลงทะเบียนไว้ """
    # ... (code for debug route) ...

# --- Health Check ---
@app.get("/health", tags=["Health Check"], include_in_schema=False)
async def health_check():
    return {"status": "ok"}

print("[*] Application setup complete. Routers included.")