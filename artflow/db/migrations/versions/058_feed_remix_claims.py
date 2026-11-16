"""Add user-scoped durable feed-remix admission and exact generation recovery.

Revision ID: 058_feed_remix_claims
Revises: 057_seedream_routing
"""
import sqlalchemy as sa
from alembic import op

revision = "058_feed_remix_claims"
down_revision = "057_seedream_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feed_remix_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("source_generation_id", sa.Integer(), nullable=False),
        sa.Column("generation_id", sa.Integer(), sa.ForeignKey("generations.id")),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("user_id", "request_key", name="uq_feed_remix_claim_user_key"),
    )


def downgrade() -> None:
    # A rollback must not discard evidence of paid/ambiguous submissions.
    if op.get_bind().execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM feed_remix_claims)")
    ).scalar():
        raise RuntimeError("Cannot drop recorded feed-remix claim evidence")
    op.drop_table("feed_remix_claims")
