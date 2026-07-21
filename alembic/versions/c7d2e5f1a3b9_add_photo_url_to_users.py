"""add photo_url to users

Revision ID: c7d2e5f1a3b9
Revises: b3c1e4f9d2a7
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7d2e5f1a3b9"
down_revision: Union[str, None] = "b3c1e4f9d2a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("photo_url", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "photo_url")
