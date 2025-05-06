"""add_rtc_fields_to_sale_item

Revision ID: 22c33ac37810
Revises: f8c637f68e22
Create Date: 2025-05-06 23:00:39.904178

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '22c33ac37810'
down_revision: Union[str, None] = 'f8c637f68e22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
