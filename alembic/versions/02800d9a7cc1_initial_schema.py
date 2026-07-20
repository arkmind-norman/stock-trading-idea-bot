"""initial_schema

Revision ID: 02800d9a7cc1
Revises:
Create Date: 2026-07-20 15:58:01.365893

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '02800d9a7cc1'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum type objects — named so Alembic emits CREATE TYPE on upgrade
# and we can drop them explicitly on downgrade.
direction_enum = sa.Enum('long', 'short', name='direction')
idea_status_enum = sa.Enum('pending', 'open', 'closed', 'rejected', name='ideastatus')
position_status_enum = sa.Enum('open', 'closed', name='positionstatus')


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('telegram_user_id', sa.String(64), nullable=False),
        sa.Column('username', sa.String(128), nullable=True),
        sa.Column('display_name', sa.String(256), nullable=False),
        sa.Column('first_idea_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('telegram_user_id'),
    )

    op.create_table(
        'ideas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('raw_text', sa.Text(), nullable=False),
        sa.Column('ticker', sa.String(16), nullable=True),
        sa.Column('direction', direction_enum, nullable=True),
        sa.Column('target_price', sa.Numeric(12, 4), nullable=True),
        sa.Column('stop_price', sa.Numeric(12, 4), nullable=True),
        sa.Column('submitted_at', sa.DateTime(), nullable=False),
        sa.Column('status', idea_status_enum, nullable=False, server_default='pending'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'positions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('idea_id', sa.Integer(), nullable=False),
        sa.Column('entry_price', sa.Numeric(12, 4), nullable=False),
        sa.Column('entry_time', sa.DateTime(), nullable=False),
        sa.Column('exit_price', sa.Numeric(12, 4), nullable=True),
        sa.Column('exit_time', sa.DateTime(), nullable=True),
        sa.Column('notional', sa.Numeric(12, 4), nullable=False),
        sa.Column('status', position_status_enum, nullable=False, server_default='open'),
        sa.Column('pnl', sa.Numeric(12, 4), nullable=True),
        sa.ForeignKeyConstraint(['idea_id'], ['ideas.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idea_id'),
    )

    op.create_table(
        'daily_equity',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('cumulative_pnl', sa.Numeric(12, 4), nullable=False),
        sa.Column('cumulative_equity', sa.Numeric(12, 4), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('user_id', 'date'),
    )

    op.create_table(
        'price_ticks',
        sa.Column('ticker', sa.String(16), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('price', sa.Numeric(12, 4), nullable=False),
        sa.PrimaryKeyConstraint('ticker', 'date'),
    )

    # Indexes to speed up the most common query patterns
    op.create_index('ix_ideas_user_id', 'ideas', ['user_id'])
    op.create_index('ix_ideas_status', 'ideas', ['status'])
    op.create_index('ix_positions_status', 'positions', ['status'])
    op.create_index('ix_daily_equity_date', 'daily_equity', ['date'])
    op.create_index('ix_price_ticks_ticker', 'price_ticks', ['ticker'])


def downgrade() -> None:
    op.drop_index('ix_price_ticks_ticker', table_name='price_ticks')
    op.drop_index('ix_daily_equity_date', table_name='daily_equity')
    op.drop_index('ix_positions_status', table_name='positions')
    op.drop_index('ix_ideas_status', table_name='ideas')
    op.drop_index('ix_ideas_user_id', table_name='ideas')

    op.drop_table('price_ticks')
    op.drop_table('daily_equity')
    op.drop_table('positions')
    op.drop_table('ideas')
    op.drop_table('users')

    # Drop PostgreSQL ENUM types — SQLAlchemy does not remove these automatically.
    position_status_enum.drop(op.get_bind(), checkfirst=True)
    idea_status_enum.drop(op.get_bind(), checkfirst=True)
    direction_enum.drop(op.get_bind(), checkfirst=True)
