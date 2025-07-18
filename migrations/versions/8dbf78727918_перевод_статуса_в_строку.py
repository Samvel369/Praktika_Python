"""Перевод статуса в строку

Revision ID: 8dbf78727918
Revises: 
Create Date: 2025-07-14 09:47:00.797943

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8dbf78727918'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('friend_request', 'status',
               existing_type=sa.BOOLEAN(),
               type_=sa.String(length=20),
               existing_nullable=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('friend_request', 'status',
               existing_type=sa.String(length=20),
               type_=sa.BOOLEAN(),
               existing_nullable=True)
    # ### end Alembic commands ###
