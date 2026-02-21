"""Add first_name, last_name, username to clients

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-21 00:00:00
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("first_name", sa.String(255), nullable=True))
    op.add_column("clients", sa.Column("last_name", sa.String(255), nullable=True))
    op.add_column("clients", sa.Column("username", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "username")
    op.drop_column("clients", "last_name")
    op.drop_column("clients", "first_name")
