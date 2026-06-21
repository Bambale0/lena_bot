"""add language to users and telegram_stars provider

Revision ID: 014_language_and_stars
Revises: 013_music_gen_type
Create Date: 2026-05-11 03:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "014_language_and_stars"
down_revision = "013_music_gen_type"


def upgrade() -> None:
    # Add language column to users
    op.add_column(
        "users",
        sa.Column("language", sa.String(8), nullable=False, server_default="ru"),
    )
    op.create_index("ix_users_language", "users", ["language"])

    # Add price_stars column to price_plans
    op.add_column(
        "price_plans",
        sa.Column("price_stars", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("price_plans", "price_stars")
    op.drop_index("ix_users_language", table_name="users")
    op.drop_column("users", "language")
