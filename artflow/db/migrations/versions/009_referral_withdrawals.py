"""add referral withdrawal requests

Revision ID: 009_referral_withdrawals
Revises: 008_generation_feed_metrics
Create Date: 2026-05-06
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "009_referral_withdrawals"
down_revision = "008_generation_feed_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    withdrawal_status = postgresql.ENUM(
        "pending",
        "approved",
        "rejected",
        name="withdrawalstatus",
        create_type=False,
    )
    withdrawal_status.create(bind, checkfirst=True)

    if "referral_withdrawal_requests" not in tables:
        op.create_table(
            "referral_withdrawal_requests",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("amount_rub", sa.Float(), nullable=False),
            sa.Column("payout_details", sa.Text(), nullable=False),
            sa.Column("status", withdrawal_status, nullable=False, server_default="pending"),
            sa.Column("admin_tg_id", sa.BigInteger(), nullable=True),
            sa.Column("admin_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_referral_withdrawal_requests_user_id",
            "referral_withdrawal_requests",
            ["user_id"],
        )
        op.create_index(
            "ix_referral_withdrawal_requests_status",
            "referral_withdrawal_requests",
            ["status"],
        )

    op.alter_column("referral_withdrawal_requests", "status", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "referral_withdrawal_requests" in tables:
        op.drop_index("ix_referral_withdrawal_requests_status", table_name="referral_withdrawal_requests")
        op.drop_index("ix_referral_withdrawal_requests_user_id", table_name="referral_withdrawal_requests")
        op.drop_table("referral_withdrawal_requests")

    sa.Enum(name="withdrawalstatus").drop(bind, checkfirst=True)
