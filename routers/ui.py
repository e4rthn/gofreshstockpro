# routers/ui.py
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
# from database import get_db # Only needed if route directly accesses DB
# from sqlalchemy.orm import Session # Only needed if route directly accesses DB

router = APIRouter(
    tags=["UI - ทั่วไป & Dashboard"],
    include_in_schema=False
)

@router.get("/", response_class=RedirectResponse, name="ui_root_redirect")
async def ui_root_redirect(request: Request):
    """ หน้าแรก (Redirect ไปหน้า Dashboard) """
    try:
        url = request.app.url_path_for("ui_dashboard")
    except Exception:
        print("Warning: Could not find route 'ui_dashboard', redirecting to products list.")
        try:
             url = request.app.url_path_for("ui_read_all_products")
        except Exception:
             url = "/ui/products/" # Absolute fallback
    return RedirectResponse(url=url)


@router.get("/ui/dashboard/", response_class=HTMLResponse, name="ui_dashboard")
async def show_dashboard(request: Request):
    """ แสดงหน้า Dashboard หลัก """
    templates = getattr(request.app.state, 'templates', None)
    if templates is None:
        return HTMLResponse("<html><body>Error: Templates not configured correctly.</body></html>", status_code=500)

    context = {"request": request}
    return templates.TemplateResponse("dashboard.html", context)