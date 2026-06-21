"""create feed remix payouts ledger

Revision ID: 025_feed_remix_payouts
Revises: 024_web_passwords_reference_urls
Create Date: 2026-06-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "025_feed_remix_payouts"
down_revision = "024_web_passwords_reference_urls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feed_remix_payouts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("generation_id", sa.Integer(), sa.ForeignKey("generations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_generation_id", sa.Integer(), sa.ForeignKey("generations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("remixer_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credits_spent", sa.Float(), nullable=False),
        sa.Column("amount_rub", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("generation_id", name="uq_feed_remix_payouts_generation_id"),
    )
    op.create_index("ix_feed_remix_payouts_generation_id", "feed_remix_payouts", ["generation_id"])
    op.create_index("ix_feed_remix_payouts_source_generation_id", "feed_remix_payouts", ["source_generation_id"])
    op.create_index("ix_feed_remix_payouts_source_user_id", "feed_remix_payouts", ["source_user_id"])
    op.create_index("ix_feed_remix_payouts_remixer_user_id", "feed_remix_payouts", ["remixer_user_id"])
    op.create_index("ix_feed_remix_payouts_created_at", "feed_remix_payouts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_feed_remix_payouts_created_at", table_name="feed_remix_payouts")
    op.drop_index("ix_feed_remix_payouts_remixer_user_id", table_name="feed_remix_payouts")
    op.drop_index("ix_feed_remix_payouts_source_user_id", table_name="feed_remix_payouts")
    op.drop_index("ix_feed_remix_payouts_source_generation_id", table_name="feed_remix_payouts")
    op.drop_index("ix_feed_remix_payouts_generation_id", table_name="feed_remix_payouts")
    op.drop_table("feed_remix_payouts")
