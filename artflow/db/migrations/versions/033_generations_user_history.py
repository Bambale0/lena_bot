"""add composite index for paginated user history

Revision ID: 033_generations_user_history
Revises: 032_payment_provider_tribute
Create Date: 2026-09-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "033_generations_user_history"
down_revision = "032_payment_provider_tribute"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_generations_user_history"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "generations" not in tables:
        return
    indexes = {item.get("name") for item in inspector.get_indexes("generations")}
    if INDEX_NAME in indexes:
        return

    op.create_index(
        INDEX_NAME,
        "generations",
        ["user_id", "created_at", "id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "generations" not in tables:
        return
    indexes = {item.get("name") for item in inspector.get_indexes("generations")}
    if INDEX_NAME in indexes:
        op.drop_index(INDEX_NAME, table_name="generations")
