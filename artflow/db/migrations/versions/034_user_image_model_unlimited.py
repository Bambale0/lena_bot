"""add per-user unlimited image model access

Revision ID: 034_user_image_model_unlimited
Revises: 033_generations_user_history
Create Date: 2026-09-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "034_user_image_model_unlimited"
down_revision = "033_generations_user_history"
branch_labels = None
depends_on = None

TABLE_NAME = "user_image_model_unlimited"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE_NAME in set(inspector.get_table_names()):
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "model_key",
            sa.String(length=64),
            sa.ForeignKey(
                "model_costs.model_key",
                ondelete="CASCADE",
                onupdate="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("created_by_admin_tg_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id",
            "model_key",
            name="uq_user_image_model_unlimited",
        ),
    )
    op.create_index(
        "ix_user_image_model_unlimited_user_id",
        TABLE_NAME,
        ["user_id"],
    )
    op.create_index(
        "ix_user_image_model_unlimited_model_key",
        TABLE_NAME,
        ["model_key"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE_NAME in set(inspector.get_table_names()):
        op.drop_table(TABLE_NAME)
