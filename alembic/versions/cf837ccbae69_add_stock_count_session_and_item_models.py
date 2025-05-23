"""Add stock count session and item models

Revision ID: cf837ccbae69
Revises: 30a6368179e3
Create Date: 2025-05-06 13:14:03.937059

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf837ccbae69'
down_revision: Union[str, None] = '30a6368179e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('stock_count_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('start_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('end_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.Enum('OPEN', 'COUNTING', 'CLOSED', 'CANCELED', name='stockcountstatus'), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('location_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_stock_count_sessions_end_date'), 'stock_count_sessions', ['end_date'], unique=False)
    op.create_index(op.f('ix_stock_count_sessions_id'), 'stock_count_sessions', ['id'], unique=False)
    op.create_index(op.f('ix_stock_count_sessions_location_id'), 'stock_count_sessions', ['location_id'], unique=False)
    op.create_index(op.f('ix_stock_count_sessions_start_date'), 'stock_count_sessions', ['start_date'], unique=False)
    op.create_index(op.f('ix_stock_count_sessions_status'), 'stock_count_sessions', ['status'], unique=False)
    op.create_table('stock_count_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('system_quantity', sa.Integer(), nullable=False),
    sa.Column('counted_quantity', sa.Integer(), nullable=True),
    sa.Column('count_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['stock_count_sessions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_stock_count_items_id'), 'stock_count_items', ['id'], unique=False)
    op.create_index(op.f('ix_stock_count_items_product_id'), 'stock_count_items', ['product_id'], unique=False)
    op.create_index(op.f('ix_stock_count_items_session_id'), 'stock_count_items', ['session_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_stock_count_items_session_id'), table_name='stock_count_items')
    op.drop_index(op.f('ix_stock_count_items_product_id'), table_name='stock_count_items')
    op.drop_index(op.f('ix_stock_count_items_id'), table_name='stock_count_items')
    op.drop_table('stock_count_items')
    op.drop_index(op.f('ix_stock_count_sessions_status'), table_name='stock_count_sessions')
    op.drop_index(op.f('ix_stock_count_sessions_start_date'), table_name='stock_count_sessions')
    op.drop_index(op.f('ix_stock_count_sessions_location_id'), table_name='stock_count_sessions')
    op.drop_index(op.f('ix_stock_count_sessions_id'), table_name='stock_count_sessions')
    op.drop_index(op.f('ix_stock_count_sessions_end_date'), table_name='stock_count_sessions')
    op.drop_table('stock_count_sessions')
    # ### end Alembic commands ###
