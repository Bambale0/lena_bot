# db/migrations/versions/001_initial.py
"""initial schema + seed data

Revision ID: 001
Revises:
Create Date: 2026-05-02
"""
import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tg_id", sa.BigInteger, nullable=False, unique=True, index=True),
        sa.Column("username", sa.String(64)),
        sa.Column("full_name", sa.String(256)),
        sa.Column("credits", sa.Integer, nullable=False, default=0),
        sa.Column("is_subscribed", sa.Boolean, nullable=False, default=False),
        sa.Column("subscription_until", sa.DateTime(timezone=True)),
        sa.Column("referrer_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("referrer_l2_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("referral_code", sa.String(32), unique=True, nullable=False),
        sa.Column("is_banned", sa.Boolean, nullable=False, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "generations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("task_id", sa.String(256)),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("gen_type", sa.Enum("image", "video", name="generationtype"), nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("result_url", sa.Text),
        sa.Column("credits_spent", sa.Integer, nullable=False, default=0),
        sa.Column(
            "status",
            sa.Enum("pending", "processing", "done", "failed", name="generationstatus"),
            nullable=False,
            default="pending",
        ),
        sa.Column("error_msg", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("amount_rub", sa.Float, nullable=False),
        sa.Column("credits", sa.Integer, nullable=False),
        sa.Column(
            "provider",
            sa.Enum("yookassa", "cryptobot", name="paymentprovider"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(256), unique=True),
        sa.Column(
            "status",
            sa.Enum("pending", "paid", "failed", "refunded", name="transactionstatus"),
            nullable=False,
            default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "price_plans",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(64), unique=True, nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("credits", sa.Integer, nullable=False),
        sa.Column("price_rub", sa.Float, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
        sa.Column("sort_order", sa.Integer, nullable=False, default=0),
    )

    op.create_table(
        "model_costs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("model_key", sa.String(64), unique=True, nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column(
            "gen_type", sa.Enum("image", "video", name="generationtype"), nullable=False
        ),
        sa.Column("credits", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
    )

    # ── Seed: price plans ──────────────────────────────────────────────────
    op.bulk_insert(
        sa.table(
            "price_plans",
            sa.column("key", sa.String),
            sa.column("label", sa.String),
            sa.column("credits", sa.Integer),
            sa.column("price_rub", sa.Float),
            sa.column("is_active", sa.Boolean),
            sa.column("sort_order", sa.Integer),
        ),
        [
            {"key": "credits_100", "label": "100 кредитов", "credits": 100, "price_rub": 199.0, "is_active": True, "sort_order": 1},
            {"key": "credits_300", "label": "300 кредитов", "credits": 300, "price_rub": 499.0, "is_active": True, "sort_order": 2},
            {"key": "credits_1000", "label": "1000 кредитов", "credits": 1000, "price_rub": 1490.0, "is_active": True, "sort_order": 3},
        ],
    )

    # ── Seed: model costs ──────────────────────────────────────────────────
    op.execute(
        sa.text(
            """
            INSERT INTO model_costs
                (model_key, display_name, gen_type, credits, is_active)
            VALUES
                ('seedream-4.5', '🌸 Seedream 4.5', 'image'::generationtype, 2, true),
                ('nano-banano-pro', '🍌 Nano Banano Pro (Gemini 3 Pro)', 'image'::generationtype, 4, true),
                ('nano-banano-2', '🍌 Nano Banano 2 (Gemini 3.1 Flash)', 'image'::generationtype, 2, true),
                ('wan-2.7', '🌊 WAN 2.7', 'image'::generationtype, 3, true),
                ('gpt-image-1', '🤖 GPT Imagine 2', 'image'::generationtype, 4, true),
                ('grok-video', '🐦 Grok Video', 'video'::generationtype, 40, true),
                ('kling-3.0', '⚡ Kling 3.0', 'video'::generationtype, 30, true),
                ('kling-2.6-motion', '🎭 Kling 2.6 Motion', 'video'::generationtype, 35, true)
            """
        )
    )


def downgrade() -> None:
    op.drop_table("model_costs")
    op.drop_table("price_plans")
    op.drop_table("transactions")
    op.drop_table("generations")
    op.drop_table("users")
