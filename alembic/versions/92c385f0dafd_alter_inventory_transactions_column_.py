"""alter_inventory_transactions_column_type_to_transactiontypeenum

Revision ID: 92c385f0dafd
Revises: 229a1e9d4027
Create Date: 2025-05-30 19:02:35.442242

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql # เพิ่ม import นี้

# revision identifiers, used by Alembic.
revision: str = '92c385f0dafd'
down_revision: Union[str, None] = '229a1e9d4027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ชื่อ ENUM type ที่ถูกต้องตาม Model
new_enum_name = 'transactiontypeenum'
# ชื่อ ENUM type เดิมที่คอลัมน์อาจจะกำลังใช้อยู่ (จาก error message)
old_enum_name_if_exists = 'transactiontype'

# ค่าของ ENUM (ควรจะตรงกับใน Python Enum และ migration 168dc19099b3)
TRANSACTION_TYPE_VALUES = ('STOCK_IN', 'SALE', 'ADJUSTMENT_ADD', 'ADJUSTMENT_SUB', 'TRANSFER_OUT', 'TRANSFER_IN', 'INITIAL')

# สร้าง object สำหรับ ENUM type ต่างๆ เผื่อใช้ (ตั้ง create_type=False เพราะเราจัดการเอง)
correct_enum_obj = postgresql.ENUM(*TRANSACTION_TYPE_VALUES, name=new_enum_name, create_type=False)
old_enum_obj_if_any = postgresql.ENUM(*TRANSACTION_TYPE_VALUES, name=old_enum_name_if_exists, create_type=False)


def upgrade() -> None:
    # ขั้นแรก, ตรวจสอบให้แน่ใจว่า ENUM type ที่ถูกต้อง (transactiontypeenum) มีอยู่แล้วใน database
    # migration 168dc19099b3 ควรจะสร้างไว้แล้ว แต่ checkfirst=True จะช่วยให้ปลอดภัย
    correct_enum_obj.create(op.get_bind(), checkfirst=True)

    print(f"Altering column 'transaction_type' in 'inventory_transactions' table to use ENUM type '{new_enum_name}'")
    # สั่ง ALTER COLUMN ให้ใช้ ENUM type ที่ถูกต้อง
    # การใช้ USING type_name::text::new_type_name เป็นวิธีมาตรฐานในการแปลง ENUM
    op.execute(
        f"ALTER TABLE inventory_transactions "
        f"ALTER COLUMN transaction_type TYPE {new_enum_name} "
        f"USING transaction_type::text::{new_enum_name};"
    )
    print(f"Column 'transaction_type' altered successfully.")

    # (ทางเลือกเสริม และต้องทำด้วยความระมัดระวัง): ถ้า ENUM type เก่า (transactiontype) ไม่มีใครใช้แล้ว
    # และคุณต้องการลบทิ้งเพื่อความสะอาด (ตรวจสอบให้แน่ใจจริงๆ ก่อนลบ)
    # คุณอาจจะต้องตรวจสอบก่อนว่ามี object อื่นยังใช้งาน transactiontype อยู่หรือไม่
    # op.execute(f"DROP TYPE IF EXISTS {old_enum_name_if_exists};")


def downgrade() -> None:
    # การ downgrade จะซับซ้อนหน่อย คือต้องเปลี่ยนกลับไปใช้ ENUM type เดิม
    # และอาจจะต้องสร้าง ENUM type เดิมขึ้นมาใหม่ถ้ามันถูกลบไปใน upgrade
    print(f"Altering column 'transaction_type' back to use ENUM type '{old_enum_name_if_exists}' (if it exists or is recreated)")

    # ตรวจสอบ/สร้าง ENUM type เก่าก่อน (ถ้าจำเป็น)
    old_enum_obj_if_any.create(op.get_bind(), checkfirst=True)

    op.execute(
        f"ALTER TABLE inventory_transactions "
        f"ALTER COLUMN transaction_type TYPE {old_enum_name_if_exists} "
        f"USING transaction_type::text::{old_enum_name_if_exists};"
    )
    print(f"Column 'transaction_type' reverted.")
    # ไม่ควรลบ new_enum_name (transactiontypeenum) ใน downgrade นี้
    # เพราะ migration อื่นๆ (เช่น 168dc19099b3) อาจจะยังต้องใช้มันอยู่