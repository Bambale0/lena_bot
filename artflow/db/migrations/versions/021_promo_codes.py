"""add promo codes

Revision ID: 021_promo_codes
Revises: 020_user_photo_url
Create Date: 2026-05-28 15:10:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "021_promo_codes"
down_revision = "020_user_photo_url"
branch_labels = None
depends_on = None


promo_reward_type = postgresql.ENUM(
    "credits",
    "discount_percent",
    "discount_amount",
    "free_generation",
    name="promorewardtype",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    promo_reward_type.create(bind, checkfirst=True)

    if "promo_codes" not in tables:
        op.create_table(
            "promo_codes",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("credits", sa.Float(), nullable=False, server_default="0"),
            sa.Column("max_redemptions", sa.Integer(), nullable=True),
            sa.Column("redeemed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by_tg_id", sa.BigInteger(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("reward_type", promo_reward_type, nullable=False),
            sa.Column("value", sa.Float(), nullable=False),
            sa.Column("max_uses", sa.Integer(), nullable=True),
            sa.Column("per_user_limit", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("uses_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code"),
        )
    else:
        columns = {col["name"] for col in inspector.get_columns("promo_codes")}
        if "reward_type" not in columns:
            op.add_column("promo_codes", sa.Column("reward_type", promo_reward_type, nullable=True))
            op.execute("UPDATE promo_codes SET reward_type = 'credits' WHERE reward_type IS NULL")
            op.alter_column("promo_codes", "reward_type", nullable=False)
        if "value" not in columns:
            op.add_column("promo_codes", sa.Column("value", sa.Float(), nullable=True))
            op.execute("UPDATE promo_codes SET value = credits WHERE value IS NULL")
            op.alter_column("promo_codes", "value", nullable=False)
        if "max_uses" not in columns:
            op.add_column("promo_codes", sa.Column("max_uses", sa.Integer(), nullable=True))
            op.execute("UPDATE promo_codes SET max_uses = max_redemptions WHERE max_uses IS NULL")
        if "per_user_limit" not in columns:
            op.add_column("promo_codes", sa.Column("per_user_limit", sa.Integer(), nullable=False, server_default="1"))
        if "uses_count" not in columns:
            op.add_column("promo_codes", sa.Column("uses_count", sa.Integer(), nullable=False, server_default="0"))
            op.execute("UPDATE promo_codes SET uses_count = redeemed_count")
        if "expires_at" not in columns:
            op.add_column("promo_codes", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
            op.execute("UPDATE promo_codes SET expires_at = valid_until WHERE expires_at IS NULL")

    indexes = {index["name"] for index in inspector.get_indexes("promo_codes")}
    if op.f("ix_promo_codes_code") not in indexes:
        op.create_index(op.f("ix_promo_codes_code"), "promo_codes", ["code"], unique=False)
    if op.f("ix_promo_codes_is_active") not in indexes:
        op.create_index(op.f("ix_promo_codes_is_active"), "promo_codes", ["is_active"], unique=False)

    tables = set(sa.inspect(bind).get_table_names())
    if "promo_redemptions" not in tables:
        op.create_table(
            "promo_redemptions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("promo_code_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("transaction_id", sa.Integer(), nullable=True),
            sa.Column("reward_type", promo_reward_type, nullable=False),
            sa.Column("value", sa.Float(), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"]),
            sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("promo_redemptions")}
    if op.f("ix_promo_redemptions_created_at") not in indexes:
        op.create_index(op.f("ix_promo_redemptions_created_at"), "promo_redemptions", ["created_at"], unique=False)
    if op.f("ix_promo_redemptions_consumed_at") not in indexes:
        op.create_index(op.f("ix_promo_redemptions_consumed_at"), "promo_redemptions", ["consumed_at"], unique=False)
    if op.f("ix_promo_redemptions_promo_code_id") not in indexes:
        op.create_index(op.f("ix_promo_redemptions_promo_code_id"), "promo_redemptions", ["promo_code_id"], unique=False)
    if op.f("ix_promo_redemptions_transaction_id") not in indexes:
        op.create_index(op.f("ix_promo_redemptions_transaction_id"), "promo_redemptions", ["transaction_id"], unique=False)
    if op.f("ix_promo_redemptions_user_id") not in indexes:
        op.create_index(op.f("ix_promo_redemptions_user_id"), "promo_redemptions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_promo_redemptions_user_id"), table_name="promo_redemptions")
    op.drop_index(op.f("ix_promo_redemptions_transaction_id"), table_name="promo_redemptions")
    op.drop_index(op.f("ix_promo_redemptions_promo_code_id"), table_name="promo_redemptions")
    op.drop_index(op.f("ix_promo_redemptions_consumed_at"), table_name="promo_redemptions")
    op.drop_index(op.f("ix_promo_redemptions_created_at"), table_name="promo_redemptions")
    op.drop_table("promo_redemptions")
    op.drop_index(op.f("ix_promo_codes_is_active"), table_name="promo_codes")
    op.drop_index(op.f("ix_promo_codes_code"), table_name="promo_codes")
    op.drop_table("promo_codes")
    promo_reward_type.drop(op.get_bind(), checkfirst=True)
