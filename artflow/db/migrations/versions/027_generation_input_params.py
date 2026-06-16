"""add generation input params

Revision ID: 027_generation_input_params
Revises: 026_suno_voices
Create Date: 2026-06-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "027_generation_input_params"
down_revision = "026_suno_voices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("generations")}
    if "input_params" not in columns:
        op.add_column("generations", sa.Column("input_params", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("generations")}
    if "input_params" in columns:
        op.drop_column("generations", "input_params")
