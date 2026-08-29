"""defer L1 referral credit reward until first paid top-up

Revision ID: 031_referral_first_topup_bonus
Revises: 030_feed_engagements
Create Date: 2026-08-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "031_referral_first_topup_bonus"
down_revision = "030_feed_engagements"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_credit_ledger_referral_first_topup"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {item.get("name") for item in inspector.get_indexes("credit_ledger")}
    if INDEX_NAME in indexes:
        return

    op.create_index(
        INDEX_NAME,
        "credit_ledger",
        ["source_type", "source_id", "entry_type"],
        unique=True,
        postgresql_where=sa.text(
            "entry_type = 'referral_first_topup_bonus' "
            "AND source_type = 'referral_user'"
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {item.get("name") for item in inspector.get_indexes("credit_ledger")}
    if INDEX_NAME in indexes:
        op.drop_index(INDEX_NAME, table_name="credit_ledger")
