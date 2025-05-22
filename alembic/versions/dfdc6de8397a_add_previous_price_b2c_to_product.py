"""add_previous_price_b2c_to_product

Revision ID: dfdc6de8397a
Revises: 61dd061cd3ff
Create Date: 2025-05-15 15:36:38.160982

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'dfdc6de8397a' # ใส่ ID ที่ถูกต้อง
down_revision: Union[str, None] = '61dd061cd3ff' # ใส่ ID ของ revision ก่อนหน้า

def upgrade() -> None:
    op.add_column('products', sa.Column('previous_price_b2c', sa.Float(), nullable=True))
    op.add_column('products', sa.Column('price_b2c_last_changed', sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column('products', 'price_b2c_last_changed')
    op.drop_column('products', 'previous_price_b2c')


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
