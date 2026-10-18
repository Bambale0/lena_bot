"""Track cumulative refunds and commit wallet/referral reversal exactly once."""

import sqlalchemy as sa
from alembic import op

revision = "045_atomic_payment_refunds"
down_revision = "044_trend_run_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_refund_notices",
        sa.Column("external_id", sa.String(256), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.add_column("transactions", sa.Column("provider_amount_minor", sa.BigInteger()))
    op.add_column("transactions", sa.Column("provider_currency", sa.String(3)))
    op.add_column("transactions", sa.Column("refunded_amount_minor", sa.BigInteger(), server_default="0", nullable=False))
    op.add_column("transactions", sa.Column("refunded_credits", sa.Float(), server_default="0", nullable=False))
    op.add_column("referral_commission_ledger", sa.Column("refund_key", sa.String(64), server_default="", nullable=False))
    op.drop_constraint("uq_referral_commission_tx_recipient_level_event", "referral_commission_ledger", type_="unique")
    op.create_unique_constraint(
        "uq_referral_commission_tx_recipient_level_event", "referral_commission_ledger",
        ["transaction_id", "recipient_user_id", "level", "event_type", "refund_key"],
    )
    op.create_table(
        "payment_refund_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("cumulative_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("credits_delta", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("transaction_id", "cumulative_amount_minor", name="uq_payment_refund_cumulative"),
    )
    op.create_index("ix_payment_refund_events_transaction_id", "payment_refund_events", ["transaction_id"])


def downgrade() -> None:
    # Preserve accounting evidence: merging several immutable partial reversal
    # rows into one old-schema row would destroy their audit trail.
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM payment_refund_events) OR EXISTS (SELECT 1 FROM payment_refund_notices)")).scalar():
        raise RuntimeError("Cannot downgrade after refunds: retain ledger and roll forward")
    op.drop_table("payment_refund_events")
    op.drop_table("payment_refund_notices")
    op.drop_constraint("uq_referral_commission_tx_recipient_level_event", "referral_commission_ledger", type_="unique")
    op.create_unique_constraint(
        "uq_referral_commission_tx_recipient_level_event", "referral_commission_ledger",
        ["transaction_id", "recipient_user_id", "level", "event_type"],
    )
    op.drop_column("referral_commission_ledger", "refund_key")
    for name in ("refunded_credits", "refunded_amount_minor", "provider_currency", "provider_amount_minor"):
        op.drop_column("transactions", name)
