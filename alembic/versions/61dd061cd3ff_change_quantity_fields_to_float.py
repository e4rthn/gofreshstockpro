from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '61dd061cd3ff'  # << ตรวจสอบให้แน่ใจว่า ID นี้ตรงกับชื่อไฟล์และค่าด้านบน
# คุณต้องหา ID ของ revision ก่อนหน้านี้มาใส่ที่ down_revision
# ดูจากไฟล์อื่นๆ ใน folder alembic/versions/ หรือ output ตอนสร้าง revision ก่อนๆ
down_revision: Union[str, None] = '168dc19099b3' # << ใส่ ID ของไฟล์ migration ก่อนหน้านี้
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.alter_column('current_stock', 'quantity',
                    existing_type=sa.INTEGER(),
                    type_=sa.FLOAT(),
                    existing_nullable=False,
                    existing_server_default=sa.text('0'))
    op.alter_column('inventory_transactions', 'quantity_change',
                    existing_type=sa.INTEGER(),
                    type_=sa.FLOAT(),
                    existing_nullable=False)
    op.alter_column('sale_items', 'quantity',
                    existing_type=sa.INTEGER(),
                    type_=sa.FLOAT(),
                    existing_nullable=False)
    # (แนะนำเพิ่มเติม) ถ้ามีการแก้ไข stock_count_items
    op.alter_column('stock_count_items', 'system_quantity',
                     existing_type=sa.INTEGER(),
                     type_=sa.FLOAT(),
                     existing_nullable=False)
    op.alter_column('stock_count_items', 'counted_quantity',
                     existing_type=sa.INTEGER(),
                     type_=sa.FLOAT(),
                     existing_nullable=True)

def downgrade() -> None:
    op.alter_column('current_stock', 'quantity',
                    existing_type=sa.FLOAT(),
                    type_=sa.INTEGER(),
                    existing_nullable=False,
                    existing_server_default=sa.text('0'))
    op.alter_column('inventory_transactions', 'quantity_change',
                    existing_type=sa.FLOAT(),
                    type_=sa.INTEGER(),
                    existing_nullable=False)
    op.alter_column('sale_items', 'quantity',
                    existing_type=sa.FLOAT(),
                    type_=sa.INTEGER(),
                    existing_nullable=False)
    # (แนะนำเพิ่มเติม) ถ้ามีการแก้ไข stock_count_items
    op.alter_column('stock_count_items', 'system_quantity',
                     existing_type=sa.FLOAT(),
                     type_=sa.INTEGER(),
                     existing_nullable=False)
    op.alter_column('stock_count_items', 'counted_quantity',
                     existing_type=sa.FLOAT(),
                     type_=sa.INTEGER(),
                     existing_nullable=True)