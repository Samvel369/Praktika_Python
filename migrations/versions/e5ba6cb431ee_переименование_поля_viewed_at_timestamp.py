"""Переименование поля viewed_at → timestamp

Revision ID: e5ba6cb431ee
Revises: 1f3edc3e1f6d
Create Date: 2025-07-16 12:49:31.628519

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5ba6cb431ee'
down_revision: Union[str, Sequence[str], None] = '1f3edc3e1f6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    pass
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    pass
    # ### end Alembic commands ###
