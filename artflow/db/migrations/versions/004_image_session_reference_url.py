"""add image session reference_url

Revision ID: 004_image_session_reference_url
Revises: 003_image_sessions
Create Date: 2026-05-05
"""
from __future__ import annotations

from alembic import op

revision = "004_image_session_reference_url"
down_revision = "003_image_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE image_sessions
        ADD COLUMN IF NOT EXISTS reference_url TEXT
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE image_sessions
        DROP COLUMN IF EXISTS reference_url
    """)
