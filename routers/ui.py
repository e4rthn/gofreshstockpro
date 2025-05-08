# routers/ui.py
from fastapi import APIRouter, Request, Depends, HTTPException # <--- เพิ่ม HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.routing import NoMatchFound # <--- Import NoMatchFound เพื่อดักจับ Error

router = APIRouter(
    tags=["UI - ทั่วไป & Dashboard"],
    include_in_schema=False
)

@router.get("/", response_class=RedirectResponse, name="ui_root_redirect")
async def ui_root_redirect(request: Request):
    """ หน้าแรก (Redirect ไปหน้า Dashboard) """
    dashboard_url = "/ui/dashboard/" # Fallback URL
    try:
        # พยายามหา URL ของ dashboard ก่อน
        dashboard_url = request.app.url_path_for("ui_dashboard")
    except NoMatchFound:
        print("Warning: Could not find route named 'ui_dashboard', using fallback '/ui/dashboard/'.")
    except Exception as e:
        print(f"Warning: Error finding dashboard route: {e}. Using fallback '/ui/dashboard/'.")

    # ลองหา URL ของ products list เป็นลำดับถัดไปถ้า dashboard ไม่มี (ไม่ควรเกิดขึ้น)
    # if dashboard_url == "/ui/dashboard/": # Check if fallback was used
    #     try:
    #          dashboard_url = request.app.url_path_for("ui_read_all_products")
    #     except Exception:
    #          dashboard_url = "/ui/products/" # Absolute fallback

    return RedirectResponse(url=dashboard_url)


@router.get("/ui/dashboard/", response_class=HTMLResponse, name="ui_dashboard")
async def show_dashboard(request: Request):
    """ แสดงหน้า Dashboard หลัก """
    templates = getattr(request.app.state, 'templates', None)
    if templates is None:
        # This should ideally not happen if setup in main.py is correct
        return HTMLResponse("<html><body>Internal Server Error: Templates not configured.</body></html>", status_code=500)

    # --- สร้าง URLs ที่ต้องการสำหรับ Navbar ที่นี่ ---
    nav_urls = {}
    route_names_needed = [
        'ui_dashboard', 'ui_show_pos_form', 'ui_view_inventory_summary',
        'ui_show_stock_in_form', 'ui_show_adjustment_form', 'ui_show_transfer_form',
        'ui_list_stock_count_sessions', 'ui_sales_report', 'ui_near_expiry_report',
        'ui_read_all_categories', 'ui_read_all_products', 'ui_read_all_locations'
        # เพิ่ม 'ui_negative_stock_report' ถ้ามี route นี้จริงๆ
    ]
    for name in route_names_needed:
        try:
            nav_urls[name.replace("ui_","")] = request.app.url_path_for(name) # สร้าง key แบบสั้นๆ
        except NoMatchFound:
            print(f"!!! CRITICAL ERROR: Could not find route named '{name}' needed for base template !!!")
            # ใน Production อาจจะ Log error หรือ return หน้า Error ทันที
            # สำหรับตอนนี้ อาจจะใส่ค่า placeholder เพื่อให้ render ต่อได้ แต่ลิงก์จะเสีย
            nav_urls[name.replace("ui_","")] = f"/error_route_not_found/{name}"
        except Exception as e:
            print(f"!!! CRITICAL ERROR: Unexpected error generating URL for '{name}': {e} !!!")
            nav_urls[name.replace("ui_","")] = f"/error_generating_url/{name}"
    # ----------------------------------------------

    context = {
        "request": request,
        "nav_urls": nav_urls # <-- ส่ง URLs ที่สร้างแล้วไปให้ Template
        }
    try:
        return templates.TemplateResponse("dashboard.html", context)
    except Exception as e:
         # ดักจับ Error ตอน Render Template (อาจเกิดจากปัญหาใน Template เอง หรือ url_path_for ในส่วนอื่น)
         print(f"!!! Error rendering dashboard template: {type(e).__name__} - {e}")
         # แสดง Traceback เพื่อ Debug
         import traceback
         traceback.print_exc()
         # คืนค่าเป็น HTML แสดงข้อผิดพลาดอย่างง่าย
         return HTMLResponse(f"<html><body><h1>Internal Server Error</h1><p>Error rendering template: {e}</p></body></html>", status_code=500)