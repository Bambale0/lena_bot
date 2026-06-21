"""add referral_balance to users

Revision ID: 011_referral_balance
Revises: 010_prompt_likes_unique_per_user
Create Date: 2026-05-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "011_referral_balance"
down_revision = "010_prompt_likes_unique_per_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("referral_balance", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "referral_balance")
