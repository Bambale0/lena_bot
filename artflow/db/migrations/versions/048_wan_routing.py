"""Audited administrator-managed Wan primary/standby and native mappings.

Revision ID: 048_wan_routing
Revises: 047_kling4_preview
"""
import sqlalchemy as sa
from alembic import op

revision = "048_wan_routing"
down_revision = "047_kling4_preview"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "wan_routing_settings",
        sa.Column("model_key", sa.String(64), primary_key=True),
        sa.Column("policy", sa.String(24), nullable=False),
        sa.Column("neironych_model_id", sa.String(80), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("updated_by_admin_tg_id", sa.BigInteger, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("model_key IN ('wan/3-0-video','wan/3-0-video-prime')", name="ck_wan_route_model"),
        sa.CheckConstraint("policy IN ('neironych_kie','neironych_only','kie_only')", name="ck_wan_route_policy"),
        sa.CheckConstraint("revision >= 0", name="ck_wan_route_revision"),
    )
    op.create_table(
        "wan_routing_audit",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("model_key", sa.String(64), nullable=False),
        sa.Column("previous_policy", sa.String(24), nullable=False),
        sa.Column("new_policy", sa.String(24), nullable=False),
        sa.Column("previous_model_id", sa.String(80), nullable=False),
        sa.Column("new_model_id", sa.String(80), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("changed_by_admin_tg_id", sa.BigInteger, nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_wan_routing_audit_model_key", "wan_routing_audit", ["model_key"])
    table = sa.table("wan_routing_settings", sa.column("model_key"), sa.column("policy"), sa.column("neironych_model_id"), sa.column("revision"))
    op.bulk_insert(table, [
        {"model_key": "wan/3-0-video", "policy": "neironych_kie", "neironych_model_id": "wan-3", "revision": 1},
        {"model_key": "wan/3-0-video-prime", "policy": "neironych_kie", "neironych_model_id": "wan-3-prime", "revision": 1},
    ])


def downgrade():
    # Keep operator choices and audit evidence; rollback is a forward repair.
    pass
