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
    from core.config import settings
    from core.wan30_routing_policy import validate_route

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
    # Carry forward effective mappings, including an explicitly empty disable
    # switch. After this one-time bootstrap the database is authoritative.
    rows = []
    for model, configured, verified_default in (
        ("wan/3-0-video", settings.WAN30_NEIRONYCH_MODEL_ID, "wan-3"),
        ("wan/3-0-video-prime", settings.WAN30_PRIME_NEIRONYCH_MODEL_ID, "wan-3-prime"),
    ):
        native = configured.strip()
        try:
            validate_route(model, "neironych_kie", native)
        except ValueError:
            # Legacy aliases outside the reviewed Wan3 contract must remain
            # operable through KIE, including in the administrator editor.
            native = ""
        rows.append({
            "model_key": model,
            "policy": "neironych_kie" if native else "kie_only",
            "neironych_model_id": native or verified_default,
            "revision": 1,
        })
    op.bulk_insert(table, rows)


def downgrade():
    # Keep operator choices and audit evidence; rollback is a forward repair.
    pass
