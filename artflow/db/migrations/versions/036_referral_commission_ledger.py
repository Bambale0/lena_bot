"""Create referral commission accounting ledger.

Revision ID: 036_referral_commission_ledger
Revises: 035_trend_user_fields
Create Date: 2026-10-01
"""

from alembic import op
import sqlalchemy as sa


revision = "036_referral_commission_ledger"
down_revision = "035_trend_user_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referral_commission_ledger",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payer_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("payment_amount_rub", sa.Float(), nullable=False),
        sa.Column("amount_rub", sa.Float(), nullable=False),
        sa.Column("balance_after_rub", sa.Float(), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False, server_default="accrual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("level BETWEEN 1 AND 3", name="ck_referral_commission_level"),
        sa.CheckConstraint("rate >= 0 AND rate <= 1", name="ck_referral_commission_rate"),
        sa.CheckConstraint("event_type IN ('accrual', 'reversal')", name="ck_referral_commission_event_type"),
        sa.UniqueConstraint(
            "transaction_id",
            "recipient_user_id",
            "level",
            "event_type",
            name="uq_referral_commission_tx_recipient_level_event",
        ),
    )
    op.create_index("ix_referral_commission_ledger_transaction_id", "referral_commission_ledger", ["transaction_id"])
    op.create_index("ix_referral_commission_ledger_payer_user_id", "referral_commission_ledger", ["payer_user_id"])
    op.create_index("ix_referral_commission_ledger_recipient_user_id", "referral_commission_ledger", ["recipient_user_id"])
    op.create_index("ix_referral_commission_ledger_event_type", "referral_commission_ledger", ["event_type"])
    op.create_index("ix_referral_commission_ledger_created_at", "referral_commission_ledger", ["created_at"])
    op.create_index(
        "ix_referral_commission_recipient_created",
        "referral_commission_ledger",
        ["recipient_user_id", "created_at"],
    )
    op.create_index(
        "ix_referral_commission_payer_created",
        "referral_commission_ledger",
        ["payer_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_referral_commission_payer_created", table_name="referral_commission_ledger")
    op.drop_index("ix_referral_commission_recipient_created", table_name="referral_commission_ledger")
    op.drop_index("ix_referral_commission_ledger_created_at", table_name="referral_commission_ledger")
    op.drop_index("ix_referral_commission_ledger_event_type", table_name="referral_commission_ledger")
    op.drop_index("ix_referral_commission_ledger_recipient_user_id", table_name="referral_commission_ledger")
    op.drop_index("ix_referral_commission_ledger_payer_user_id", table_name="referral_commission_ledger")
    op.drop_index("ix_referral_commission_ledger_transaction_id", table_name="referral_commission_ledger")
    op.drop_table("referral_commission_ledger")
