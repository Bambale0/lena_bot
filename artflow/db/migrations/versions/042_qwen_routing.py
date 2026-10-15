"""Admin-controlled, audited provider routing for Qwen-facing workflows.

Revision ID: 042_qwen_routing
Revises: 041_feed_photo1_identity_default
"""
import sqlalchemy as sa
from alembic import op

revision = "042_qwen_routing"
down_revision = "041_feed_photo1_identity_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qwen_routing_settings",
        sa.Column("mode", sa.String(16), primary_key=True),
        sa.Column("primary_provider", sa.String(16), nullable=False),
        sa.Column("backup_provider", sa.String(16), nullable=True),
        sa.Column("updated_by_admin_tg_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("mode IN ('text','image','video')", name="ck_qwen_routing_mode"),
        sa.CheckConstraint("primary_provider IN ('neironych','kie')", name="ck_qwen_routing_primary"),
        sa.CheckConstraint("backup_provider IS NULL OR backup_provider IN ('neironych','kie')", name="ck_qwen_routing_backup"),
        sa.CheckConstraint("backup_provider IS NULL OR backup_provider <> primary_provider", name="ck_qwen_routing_distinct"),
    )
    op.create_table(
        "qwen_routing_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("previous_primary_provider", sa.String(16), nullable=False),
        sa.Column("previous_backup_provider", sa.String(16), nullable=True),
        sa.Column("new_primary_provider", sa.String(16), nullable=False),
        sa.Column("new_backup_provider", sa.String(16), nullable=True),
        sa.Column("changed_by_admin_tg_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_qwen_routing_audit_mode", "qwen_routing_audit", ["mode"])


def downgrade() -> None:
    op.drop_index("ix_qwen_routing_audit_mode", table_name="qwen_routing_audit")
    op.drop_table("qwen_routing_audit")
    op.drop_table("qwen_routing_settings")
