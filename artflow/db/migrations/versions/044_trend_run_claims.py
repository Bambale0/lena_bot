"""Guard paid trend submissions with a durable user-scoped request key.

Revision ID: 044_trend_run_claims
Revises: 043_wan30_pricing
"""

import sqlalchemy as sa
from alembic import op

revision = "044_trend_run_claims"
down_revision = "043_wan30_pricing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trend_run_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("trend_id", sa.Integer(), nullable=False),
        sa.Column("generation_id", sa.Integer(), sa.ForeignKey("generations.id")),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "request_key", name="uq_trend_run_claim_user_key"),
    )


def downgrade() -> None:
    op.drop_table("trend_run_claims")
