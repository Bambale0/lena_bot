"""add source_feed_gen_id and is_prompt_library to generations

Revision ID: 012_feed_remix_royalty
Revises: 011_referral_balance
Create Date: 2026-05-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "012_feed_remix_royalty"
down_revision = "011_referral_balance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generations",
        sa.Column("source_feed_gen_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "generations",
        sa.Column("is_prompt_library", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_foreign_key(
        "fk_generations_source_feed_gen_id",
        "generations", "generations",
        ["source_feed_gen_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_generations_source_feed_gen_id", "generations", type_="foreignkey")
    op.drop_column("generations", "source_feed_gen_id")
    op.drop_column("generations", "is_prompt_library")
