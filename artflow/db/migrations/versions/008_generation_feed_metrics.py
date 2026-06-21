"""add generation feed metrics

Revision ID: 008_generation_feed_metrics
Revises: 007_image_session_ref_files
Create Date: 2026-05-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "008_generation_feed_metrics"
down_revision = "007_image_session_ref_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("generations")}

    if "is_public_feed" not in columns:
        op.add_column(
            "generations",
            sa.Column("is_public_feed", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    if "likes_count" not in columns:
        op.add_column(
            "generations",
            sa.Column("likes_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if "shares_count" not in columns:
        op.add_column(
            "generations",
            sa.Column("shares_count", sa.Integer(), nullable=False, server_default="0"),
        )

    op.alter_column("generations", "is_public_feed", server_default=None)
    op.alter_column("generations", "likes_count", server_default=None)
    op.alter_column("generations", "shares_count", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("generations")}

    if "shares_count" in columns:
        op.drop_column("generations", "shares_count")
    if "likes_count" in columns:
        op.drop_column("generations", "likes_count")
    if "is_public_feed" in columns:
        op.drop_column("generations", "is_public_feed")
