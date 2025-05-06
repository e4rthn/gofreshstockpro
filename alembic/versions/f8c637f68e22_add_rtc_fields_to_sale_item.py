"""add_rtc_fields_to_sale_item

Revision ID: f8c637f68e22
Revises: cf837ccbae69
Create Date: 2025-05-06 23:00:23.025159

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8c637f68e22'
down_revision: Union[str, None] = 'cf837ccbae69'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
