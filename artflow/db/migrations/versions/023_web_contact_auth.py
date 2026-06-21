"""add web contact auth

Revision ID: 023_web_contact_auth
Revises: 022_payment_provider_lava
Create Date: 2026-06-04 12:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "023_web_contact_auth"
down_revision = "022_payment_provider_lava"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {col["name"] for col in inspector.get_columns("users")}
    if "email" not in user_columns:
        op.add_column("users", sa.Column("email", sa.String(length=256), nullable=True))
        op.create_index("ix_users_email", "users", ["email"], unique=True)
    if "phone" not in user_columns:
        op.add_column("users", sa.Column("phone", sa.String(length=32), nullable=True))
        op.create_index("ix_users_phone", "users", ["phone"], unique=True)

    if "web_auth_codes" not in set(inspector.get_table_names()):
        op.create_table(
            "web_auth_codes",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("contact_type", sa.String(length=16), nullable=False),
            sa.Column("contact", sa.String(length=256), nullable=False),
            sa.Column("code_hash", sa.String(length=128), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("contact_type", "contact", "code_hash", name="uq_web_auth_codes_contact_hash"),
        )
        op.create_index("ix_web_auth_codes_contact_type", "web_auth_codes", ["contact_type"])
        op.create_index("ix_web_auth_codes_contact", "web_auth_codes", ["contact"])
        op.create_index("ix_web_auth_codes_expires_at", "web_auth_codes", ["expires_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "web_auth_codes" in set(inspector.get_table_names()):
        op.drop_index("ix_web_auth_codes_expires_at", table_name="web_auth_codes")
        op.drop_index("ix_web_auth_codes_contact", table_name="web_auth_codes")
        op.drop_index("ix_web_auth_codes_contact_type", table_name="web_auth_codes")
        op.drop_table("web_auth_codes")
    user_columns = {col["name"] for col in inspector.get_columns("users")}
    if "phone" in user_columns:
        op.drop_index("ix_users_phone", table_name="users")
        op.drop_column("users", "phone")
    if "email" in user_columns:
        op.drop_index("ix_users_email", table_name="users")
        op.drop_column("users", "email")
