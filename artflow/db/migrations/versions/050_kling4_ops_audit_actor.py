"""Record trusted-shell Kling rollout actors without Telegram impersonation.

Revision ID: 050_kling4_ops_audit_actor
Revises: 049_trend_runtime_model_repair
"""

import sqlalchemy as sa
from alembic import op

revision = "050_kling4_ops_audit_actor"
down_revision = "049_trend_runtime_model_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("kling4_access_audit") as batch:
        batch.alter_column(
            "changed_by_admin_tg_id",
            existing_type=sa.BigInteger(),
            nullable=True,
        )
        batch.add_column(sa.Column("changed_by_operator", sa.String(128), nullable=True))
        batch.create_check_constraint(
            "ck_kling4_access_audit_actor",
            "(source IN ('web','bot') AND changed_by_admin_tg_id IS NOT NULL "
            "AND changed_by_operator IS NULL) OR "
            "(source = 'ops' AND changed_by_admin_tg_id IS NULL "
            "AND changed_by_operator IS NOT NULL)",
        )


def downgrade() -> None:
    raise RuntimeError(
        "Kling 4 actor provenance is immutable release evidence; roll forward instead"
    )
