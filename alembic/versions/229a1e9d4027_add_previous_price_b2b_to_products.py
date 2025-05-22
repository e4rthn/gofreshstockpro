"""add_previous_price_b2b_to_products

Revision ID: 229a1e9d4027
Revises: 0fd2767ace7a
Create Date: 2025-05-15 15:51:00.194302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '229a1e9d4027'
down_revision: Union[str, None] = '0fd2767ace7a' # <<< ID ของ migration ก่อนหน้าที่เพิ่ม previous_price_b2c

branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    print("Adding column: products.previous_price_b2b")
    op.add_column('products', sa.Column('previous_price_b2b', sa.Float(), nullable=True))
    
    print("Adding column: products.price_b2b_last_changed")
    op.add_column('products', sa.Column('price_b2b_last_changed', sa.DateTime(timezone=True), nullable=True))
    print("Columns previous_price_b2b and price_b2b_last_changed added to products table.")


def downgrade() -> None:
    print("Dropping column: products.price_b2b_last_changed")
    op.drop_column('products', 'price_b2b_last_changed')
    
    print("Dropping column: products.previous_price_b2b")
    op.drop_column('products', 'previous_price_b2b')
    print("Columns previous_price_b2b and price_b2b_last_changed dropped from products table.")