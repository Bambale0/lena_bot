"""Record trusted-shell Qwen routing actors without Telegram impersonation.

Revision ID: 051_qwen_ops_audit_actor
Revises: 050_kling4_ops_audit_actor
"""

import sqlalchemy as sa
from alembic import op

revision = "051_qwen_ops_audit_actor"
down_revision = "050_kling4_ops_audit_actor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("qwen_routing_audit") as batch:
        batch.alter_column(
            "changed_by_admin_tg_id",
            existing_type=sa.BigInteger(),
            nullable=True,
        )
        batch.add_column(sa.Column("changed_by_operator", sa.String(128), nullable=True))
        batch.create_check_constraint(
            "ck_qwen_routing_audit_actor",
            "(source IN ('web','telegram') AND changed_by_admin_tg_id IS NOT NULL "
            "AND changed_by_operator IS NULL) OR "
            "(source = 'ops' AND changed_by_admin_tg_id IS NULL "
            "AND changed_by_operator IS NOT NULL)",
        )


def downgrade() -> None:
    raise RuntimeError(
        "Qwen routing actor provenance is immutable release evidence; roll forward instead"
    )
