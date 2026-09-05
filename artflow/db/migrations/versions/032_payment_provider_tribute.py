"""add tribute payment provider

Revision ID: 032_payment_provider_tribute
Revises: 031_referral_first_topup_bonus
Create Date: 2026-09-05
"""
from alembic import op

revision = "032_payment_provider_tribute"
down_revision = "031_referral_first_topup_bonus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE paymentprovider ADD VALUE IF NOT EXISTS 'tribute'")


def downgrade() -> None:
    # PostgreSQL enums cannot safely drop values in-place.
    pass
