# routers/ui.py
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

# Prefix จะถูกกำหนดใน main.py ตอน include_router
router = APIRouter(
    tags=["UI - ทั่วไป"],
    include_in_schema=False # ซ่อน UI routes จาก OpenAPI schema (/docs)
)

@router.get("/", response_class=RedirectResponse, name="ui_root_redirect")
async def ui_root_redirect(request: Request):
    """ หน้าแรก (Redirect ไปหน้ารายการสินค้า) """
    try:
        # ใช้ request.app.url_path_for เพื่อความถูกต้องในการสร้าง URL จากชื่อ route
        # ชื่อ route "ui_read_all_products" ถูกกำหนดใน routers/products.py
        url = request.app.url_path_for("ui_read_all_products")
        return RedirectResponse(url=url)
    except Exception as e:
        print(f"Error generating URL for ui_read_all_products: {e}")
        # Fallback ถ้าหาชื่อ route ไม่เจอ หรือมีปัญหา
        return RedirectResponse(url="/ui/products/")