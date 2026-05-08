"""add prompt likes table with unique user constraint

Revision ID: 010_prompt_likes_unique_per_user
Revises: 009_referral_withdrawals
Create Date: 2026-05-07
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "010_prompt_likes_unique_per_user"
down_revision = "009_referral_withdrawals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "prompt_likes" not in tables:
        op.create_table(
            "prompt_likes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("prompt_id", sa.Integer(), sa.ForeignKey("user_prompts.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", "prompt_id", name="uq_prompt_likes_user_prompt"),
        )
        op.create_index("ix_prompt_likes_user_id", "prompt_likes", ["user_id"])
        op.create_index("ix_prompt_likes_prompt_id", "prompt_likes", ["prompt_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "prompt_likes" in tables:
        op.drop_index("ix_prompt_likes_prompt_id", table_name="prompt_likes")
        op.drop_index("ix_prompt_likes_user_id", table_name="prompt_likes")
        op.drop_table("prompt_likes")
