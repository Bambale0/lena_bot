"""add photo_url to users

Revision ID: 020_user_photo_url
Revises: 019_generation_result_urls
Create Date: 2026-05-20 21:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "020_user_photo_url"
down_revision = "019_generation_result_urls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("photo_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "photo_url")
