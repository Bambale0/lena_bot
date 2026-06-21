"""add result_urls to generations

Revision ID: 019_generation_result_urls
Revises: 018_credit_ledger
Create Date: 2026-05-16 13:45:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "019_generation_result_urls"
down_revision = "018_credit_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("generations", sa.Column("result_urls", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("generations", "result_urls")
