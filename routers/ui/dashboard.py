# routers/ui/dashboard.py
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.routing import NoMatchFound

ui_router = APIRouter(
    prefix="/ui",
    tags=["UI - Dashboard & General"],
    include_in_schema=False
)

# --- Root Redirect ถูกย้ายไป main.py แล้ว ---
# @ui_router.get("/", response_class=RedirectResponse, name="ui_root_redirect", ...)

@ui_router.get("/dashboard/", response_class=HTMLResponse, name="ui_dashboard")
async def show_dashboard(request: Request):
    """ แสดงหน้า Dashboard หลัก """
    templates = getattr(request.app.state, 'templates', None)
    if templates is None:
        return HTMLResponse("<html><body>Internal Server Error: Templates not configured.</body></html>", status_code=500)

    context = {"request": request} # ส่งแค่ request

    try:
        return templates.TemplateResponse("dashboard.html", context)
    except Exception as e:
         print(f"!!! Error rendering dashboard template: {type(e).__name__} - {e}")
         import traceback
         traceback.print_exc()
         return HTMLResponse(f"<html><body><h1>Internal Server Error</h1><p>Error rendering template: {e}</p></body></html>", status_code=500)