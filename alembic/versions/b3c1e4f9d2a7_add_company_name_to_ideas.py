"""add company_name to ideas

Revision ID: b3c1e4f9d2a7
Revises: 02800d9a7cc1
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3c1e4f9d2a7"
down_revision: Union[str, None] = "02800d9a7cc1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ideas", sa.Column("company_name", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("ideas", "company_name")
