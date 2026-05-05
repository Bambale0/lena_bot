"""merge image session migration heads

Revision ID: 005_merge_image_session_heads
Revises: 004_image_session_last_prompt, 004_image_session_reference_url
Create Date: 2026-05-05
"""
from __future__ import annotations

revision = "005_merge_image_session_heads"
down_revision = ("004_image_session_last_prompt", "004_image_session_reference_url")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
