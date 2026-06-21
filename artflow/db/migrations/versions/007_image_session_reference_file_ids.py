"""add image session reference_file_ids

Revision ID: 007_image_session_ref_files
Revises: 006_prompt_library_showcase
Create Date: 2026-05-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "007_image_session_ref_files"
down_revision = "006_prompt_library_showcase"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("image_sessions")}
    if "reference_file_ids" not in columns:
        op.add_column("image_sessions", sa.Column("reference_file_ids", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("image_sessions")}
    if "reference_file_ids" in columns:
        op.drop_column("image_sessions", "reference_file_ids")
