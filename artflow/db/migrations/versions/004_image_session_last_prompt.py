"""Add last_prompt to image sessions.

Revision ID: 004_image_session_last_prompt
Revises: 003_image_sessions
Create Date: 2026-05-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "004_image_session_last_prompt"
down_revision = "003_image_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("image_sessions")}
    if "last_prompt" not in columns:
        op.add_column("image_sessions", sa.Column("last_prompt", sa.Text(), nullable=True))
        op.execute("UPDATE image_sessions SET last_prompt = base_prompt WHERE last_prompt IS NULL")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("image_sessions")}
    if "last_prompt" in columns:
        op.drop_column("image_sessions", "last_prompt")
