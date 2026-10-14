"""Add provider-scoped, audited image refund deadlines.

Revision ID: 039_image_recovery_policy
Revises: 038_image_session_provenance
"""
import sqlalchemy as sa
from alembic import op

revision = "039_image_recovery_policy"
down_revision = "038_image_session_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "image_recovery_policies",
        sa.Column("provider", sa.String(32), primary_key=True),
        sa.Column("auto_refund_seconds", sa.Integer, nullable=False),
        sa.Column("updated_by_admin_tg_id", sa.BigInteger, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("provider IN ('neironych','nexus')", name="ck_image_recovery_provider"),
        sa.CheckConstraint("auto_refund_seconds BETWEEN 600 AND 86400", name="ck_image_recovery_seconds"),
    )
    op.create_table(
        "image_recovery_policy_audit",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("previous_seconds", sa.Integer, nullable=False),
        sa.Column("new_seconds", sa.Integer, nullable=False),
        sa.Column("changed_by_admin_tg_id", sa.BigInteger, nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("provider IN ('neironych','nexus')", name="ck_image_recovery_audit_provider"),
    )
    op.create_index("ix_image_recovery_policy_audit_provider", "image_recovery_policy_audit", ["provider"])


def downgrade() -> None:
    op.drop_index("ix_image_recovery_policy_audit_provider", table_name="image_recovery_policy_audit")
    op.drop_table("image_recovery_policy_audit")
    op.drop_table("image_recovery_policies")
