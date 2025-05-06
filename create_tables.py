# create_tables.py
import database

# Import Models ทุกตัวที่เราสร้าง เพื่อให้ Base รู้จักแน่นอน
# การ import ผ่าน __init__ อาจจะไม่พอในบางกรณีเมื่อรันสคริปต์แยก
print("Importing models...")
try:
    # Import models ที่เราสร้างขึ้น
    from models.category import Category
    from models.product import Product
    # ถ้ามี models อื่นๆ ก็ import เพิ่มที่นี่
    print("Models imported successfully.")
except ImportError as e:
    print(f"!!! Error importing models: {e}")
    print("!!! Make sure models exist and there are no circular imports.")
    exit() # ออกจากสคริปต์ถ้า import ไม่ได้

def main():
    print("Attempting to connect to the database engine...")
    if not database.engine:
        print("!!! Database engine is not configured in database.py.")
        print("!!! Please check .env file and database connection settings.")
        return

    # แสดง URL (ซ่อนรหัสผ่าน) เพื่อตรวจสอบ
    print(f"Using database engine: {database.engine.url.render_as_string(hide_password=True)}")
    print(f"Found Models linked to Base: {list(database.Base.metadata.tables.keys())}")

    if not database.Base.metadata.tables:
        print("!!! No tables found associated with Base metadata. Cannot create tables.")
        return

    print("Attempting to create database tables defined in models...")

    try:
        # สั่งสร้างตารางทั้งหมดที่ผูกกับ Base
        database.Base.metadata.create_all(bind=database.engine)
        print("✅ Database tables check/creation process completed successfully.")
        print("ℹ️ Please check the Supabase Table Editor again (you might need to refresh the page).")
    except Exception as e:
        print(f"!!! An error occurred during table creation: {e}")
        print("!!! Please check database connection details, user permissions, and model definitions.")

if __name__ == "__main__":
    # ตรวจสอบว่า engine ถูกสร้างใน database.py หรือไม่ก่อนเรียก main
    if database.engine:
         main()
    else:
         print("Exiting script because database engine is not available.")