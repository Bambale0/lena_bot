"""add user-level feed engagement dedupe

Revision ID: 030_feed_engagements
Revises: 029_grok_15_pricing
Create Date: 2026-08-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "030_feed_engagements"
down_revision = "029_grok_15_pricing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "feed_engagements" not in tables:
        op.create_table(
            "feed_engagements",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "generation_id",
                sa.Integer(),
                sa.ForeignKey("generations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("action", sa.String(length=16), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "user_id",
                "generation_id",
                "action",
                name="uq_feed_engagement_user_generation_action",
            ),
            sa.CheckConstraint(
                "action IN ('like', 'share')",
                name="ck_feed_engagement_action",
            ),
        )
        op.create_index("ix_feed_engagements_user_id", "feed_engagements", ["user_id"])
        op.create_index(
            "ix_feed_engagements_generation_id",
            "feed_engagements",
            ["generation_id"],
        )
        op.create_index("ix_feed_engagements_action", "feed_engagements", ["action"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "feed_engagements" in tables:
        op.drop_index("ix_feed_engagements_action", table_name="feed_engagements")
        op.drop_index("ix_feed_engagements_generation_id", table_name="feed_engagements")
        op.drop_index("ix_feed_engagements_user_id", table_name="feed_engagements")
        op.drop_table("feed_engagements")
