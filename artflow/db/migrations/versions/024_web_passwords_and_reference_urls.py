"""add web passwords and image session reference urls

Revision ID: 024_web_passwords_reference_urls
Revises: 023_web_contact_auth
Create Date: 2026-06-09 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "024_web_passwords_reference_urls"
down_revision = "023_web_contact_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    user_columns = {col["name"] for col in inspector.get_columns("users")}
    if "password_hash" not in user_columns:
        op.add_column("users", sa.Column("password_hash", sa.String(length=256), nullable=True))
    if "password_set_at" not in user_columns:
        op.add_column("users", sa.Column("password_set_at", sa.DateTime(timezone=True), nullable=True))

    session_columns = {col["name"] for col in inspector.get_columns("image_sessions")}
    if "reference_urls" not in session_columns:
        op.add_column("image_sessions", sa.Column("reference_urls", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    session_columns = {col["name"] for col in inspector.get_columns("image_sessions")}
    if "reference_urls" in session_columns:
        op.drop_column("image_sessions", "reference_urls")

    user_columns = {col["name"] for col in inspector.get_columns("users")}
    if "password_set_at" in user_columns:
        op.drop_column("users", "password_set_at")
    if "password_hash" in user_columns:
        op.drop_column("users", "password_hash")
