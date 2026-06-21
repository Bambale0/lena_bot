"""add music to generationtype enum

Revision ID: 013_music_gen_type
Revises: 012_feed_remix_royalty
Create Date: 2026-05-09
"""
from __future__ import annotations

from alembic import op

revision = "013_music_gen_type"
down_revision = "012_feed_remix_royalty"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE generationtype ADD VALUE IF NOT EXISTS 'music'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — no-op
    pass
