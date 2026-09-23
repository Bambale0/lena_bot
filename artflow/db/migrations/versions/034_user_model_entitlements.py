"""add per-user model entitlements

Revision ID: 034_user_model_entitlements
Revises: 033_generations_user_history
Create Date: 2026-09-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "034_user_model_entitlements"
down_revision = "033_generations_user_history"
branch_labels = None
depends_on = None

TABLE_NAME = "user_model_entitlements"
INDEX_NAME = "ix_user_model_entitlements_user_id"
UNIQUE_NAME = "uq_user_model_entitlement_user_model"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE_NAME in set(inspector.get_table_names()):
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_key", sa.String(length=64), nullable=False),
        sa.Column("is_unlimited", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_tg_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "model_key", name=UNIQUE_NAME),
    )
    op.create_index(INDEX_NAME, TABLE_NAME, ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE_NAME in set(inspector.get_table_names()):
        op.drop_table(TABLE_NAME)
