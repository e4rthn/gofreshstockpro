# main.py
import os
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse # สำหรับ Error Handler (ถ้ามี)
import datetime

# กำหนด Path ให้ถูกต้อง อิงจากตำแหน่งของ main.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.globals['current_year'] = datetime.datetime.utcnow().year

# --- ใช้ Absolute Import จาก Project Root (gofresh_stockpro) ---
from routers import categories, products, locations, inventory, ui, sales, stock_count
# -----------------------------------------------------------------

app = FastAPI(title="GoFresh StockPro - ระบบจัดการสต็อก")
app.state.templates = templates # ทำให้ templates เข้าถึงได้ผ่าน request.app.state
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ========== Include Routers ==========
API_INCLUDE_IN_SCHEMA = True # ตั้งเป็น True เพื่อให้เห็น API ใน /docs
# API Routers (กำหนด prefix ที่นี่)
app.include_router(categories.router, prefix="/api/categories", tags=["API - หมวดหมู่สินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(products.router, prefix="/api/products", tags=["API - สินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(locations.router, prefix="/api/locations", tags=["API - สถานที่จัดเก็บ"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(inventory.router, prefix="/api/inventory", tags=["API - สต็อกสินค้า"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(sales.router, prefix="/api/sales", tags=["API - การขาย (Sales)"], include_in_schema=API_INCLUDE_IN_SCHEMA)
app.include_router(stock_count.router, prefix="/api/stock-counts", tags=["API - ตรวจนับสต็อก"], include_in_schema=API_INCLUDE_IN_SCHEMA)

# --- UI Routers (prefix ถูกกำหนดในแต่ละ router file หรือที่นี่) ---
app.include_router(ui.router) # prefix="/" (สำหรับหน้าแรก)
app.include_router(categories.ui_router) # prefix="/ui/categories"
app.include_router(products.ui_router)   # prefix="/ui/products"
app.include_router(locations.ui_router)  # prefix="/ui/locations"
app.include_router(inventory.ui_router)  # prefix="/ui/inventory"
app.include_router(sales.ui_router, prefix="/ui") #(ภายในมี /pos, /sales/report)
app.include_router(stock_count.ui_router)# prefix="/ui/stock-counts"

# ส่วน Alembic และการสร้างตาราง ควรจัดการผ่านคำสั่ง alembic โดยตรง
# from database import engine, Base
# Base.metadata.create_all(bind=engine)