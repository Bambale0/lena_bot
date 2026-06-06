"""add lava payment provider

Revision ID: 022_payment_provider_lava
Revises: 021_promo_codes
Create Date: 2026-06-03 01:30:00
"""
from alembic import op

revision = "022_payment_provider_lava"
down_revision = "021_promo_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE paymentprovider ADD VALUE IF NOT EXISTS 'lava'")


def downgrade() -> None:
    pass
