"""add credit ledger

Revision ID: 018_credit_ledger
Revises: 017_prompt_ai_moderation_audit
Create Date: 2026-05-13 20:55:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "018_credit_ledger"
down_revision = "017_prompt_ai_moderation_audit"


def upgrade() -> None:
    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False),
        sa.Column("balance_after", sa.Float(), nullable=False),
        sa.Column("entry_type", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_credit_ledger_user_id", "credit_ledger", ["user_id"])
    op.create_index("ix_credit_ledger_entry_type", "credit_ledger", ["entry_type"])
    op.create_index("ix_credit_ledger_source_type", "credit_ledger", ["source_type"])
    op.create_index("ix_credit_ledger_source_id", "credit_ledger", ["source_id"])
    op.create_index("ix_credit_ledger_created_at", "credit_ledger", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_credit_ledger_created_at", table_name="credit_ledger")
    op.drop_index("ix_credit_ledger_source_id", table_name="credit_ledger")
    op.drop_index("ix_credit_ledger_source_type", table_name="credit_ledger")
    op.drop_index("ix_credit_ledger_entry_type", table_name="credit_ledger")
    op.drop_index("ix_credit_ledger_user_id", table_name="credit_ledger")
    op.drop_table("credit_ledger")
