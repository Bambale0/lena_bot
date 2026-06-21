"""add telegram_stars payment provider

Revision ID: 016_stars_provider
Revises: 015_float_credits
Create Date: 2026-05-11 16:40:00
"""
from alembic import op

revision = "016_stars_provider"
down_revision = "015_float_credits"


def upgrade() -> None:
    op.execute("ALTER TYPE paymentprovider ADD VALUE IF NOT EXISTS 'telegram_stars'")


def downgrade() -> None:
    # PostgreSQL enums cannot safely drop values in-place.
    pass
