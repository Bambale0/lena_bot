"""add tbank payment provider

Revision ID: 002
Revises: 001
Create Date: 2026-05-04
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE paymentprovider ADD VALUE IF NOT EXISTS 'tbank'")


def downgrade() -> None:
    pass
