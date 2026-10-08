"""Add typed, auditable runtime routing for the Nano Banana 2.1 model.

Revision ID: 037_provider_routing_settings
Revises: 036_referral_commission_ledger
"""
import sqlalchemy as sa
from alembic import op

revision = "037_provider_routing_settings"
down_revision = "036_referral_commission_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_routing_settings",
        sa.Column("model_key", sa.String(64), primary_key=True),
        sa.Column("primary_provider", sa.String(32), nullable=False),
        sa.Column("updated_by_admin_tg_id", sa.BigInteger, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("primary_provider IN ('neironych','nexus')", name="ck_provider_routing_provider"),
    )
    op.create_table(
        "provider_routing_audit",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("model_key", sa.String(64), nullable=False),
        sa.Column("previous_provider", sa.String(32), nullable=True),
        sa.Column("new_provider", sa.String(32), nullable=False),
        sa.Column("changed_by_admin_tg_id", sa.BigInteger, nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("new_provider IN ('neironych','nexus')", name="ck_provider_routing_audit_new_provider"),
    )
    op.create_index("ix_provider_routing_audit_model_key", "provider_routing_audit", ["model_key"])


def downgrade() -> None:
    op.drop_index("ix_provider_routing_audit_model_key", table_name="provider_routing_audit")
    op.drop_table("provider_routing_audit")
    op.drop_table("provider_routing_settings")
