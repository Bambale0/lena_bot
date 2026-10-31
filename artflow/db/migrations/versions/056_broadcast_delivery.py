"""Add durable Telegram broadcast queue and delivery audit.

Revision ID: 056_broadcast_delivery
Revises: 055_referral_credit
"""

import sqlalchemy as sa
from alembic import op

revision = "056_broadcast_delivery"
down_revision = "055_referral_credit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_telegram_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_users_last_telegram_activity_at",
        "users",
        ["last_telegram_activity_at"],
    )

    op.create_table(
        "broadcast_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
        sa.Column("segment", sa.String(16), nullable=False),
        sa.Column("source_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("source_message_id", sa.Integer(), nullable=False),
        sa.Column("created_by_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="preparing"),
        sa.Column("selected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "preselection_skipped_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("report_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("report_message_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('preparing', 'queued', 'running', 'completed')",
            name="ck_broadcast_runs_status",
        ),
    )
    op.create_index(
        "ix_broadcast_runs_due",
        "broadcast_runs",
        ["status", "scheduled_for"],
    )

    op.create_table(
        "broadcast_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.String(32),
            sa.ForeignKey("broadcast_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("telegram_message_id", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_detail", sa.String(256), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'delivered', 'skipped', 'failed', 'uncertain')",
            name="ck_broadcast_deliveries_status",
        ),
        sa.UniqueConstraint(
            "run_id",
            "user_id",
            name="uq_broadcast_delivery_run_user",
        ),
        sa.UniqueConstraint(
            "run_id",
            "tg_id",
            name="uq_broadcast_delivery_run_tg",
        ),
    )
    op.create_index(
        "ix_broadcast_deliveries_run_status",
        "broadcast_deliveries",
        ["run_id", "status", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_broadcast_deliveries_run_status",
        table_name="broadcast_deliveries",
    )
    op.drop_table("broadcast_deliveries")
    op.drop_index("ix_broadcast_runs_due", table_name="broadcast_runs")
    op.drop_table("broadcast_runs")
    op.drop_index("ix_users_last_telegram_activity_at", table_name="users")
    op.drop_column("users", "last_telegram_activity_at")
