"""add personalized trend fields

Revision ID: 033_trend_user_fields
Revises: 032_payment_provider_tribute
Create Date: 2026-09-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "033_trend_user_fields"
down_revision = "032_payment_provider_tribute"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_prompts",
        sa.Column("trend_user_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )


def downgrade() -> None:
    op.drop_column("user_prompts", "trend_user_fields")
