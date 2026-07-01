"""Expand prompt marketplace into visual prompt library.

Revision ID: 006_prompt_library_showcase
Revises: 005_merge_image_session_heads
Create Date: 2026-05-06
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "006_prompt_library_showcase"
down_revision = "005_merge_image_session_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    user_columns = {col["name"] for col in inspector.get_columns("users")}
    if "referrer_l3_id" not in user_columns:
        op.add_column("users", sa.Column("referrer_l3_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_users_referrer_l3_id_users",
            "users",
            "users",
            ["referrer_l3_id"],
            ["id"],
        )

    if not inspector.has_table("user_prompts"):
        op.create_table(
            "user_prompts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("title", sa.String(length=60), nullable=False),
            sa.Column("description", sa.String(length=200), nullable=False),
            sa.Column(
                "category",
                sa.Enum("art", "business", "marketing", "photo", "other", name="promptcategory"),
                nullable=False,
            ),
            sa.Column("prompt_text", sa.Text(), nullable=False),
            sa.Column("preview_url", sa.Text(), nullable=True),
            sa.Column("model", sa.String(length=64), nullable=True),
            sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
            sa.Column("likes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column(
                "status",
                sa.Enum("pending", "approved", "rejected", "deactivated", name="promptstatus"),
                nullable=False,
                server_default="pending",
                index=True,
            ),
            sa.Column("reject_reason", sa.String(length=500), nullable=True),
            sa.Column("uses_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.alter_column("user_prompts", "tags", server_default=None)
        op.alter_column("user_prompts", "likes", server_default=None)
        op.alter_column("user_prompts", "is_public", server_default=None)
        op.alter_column("user_prompts", "status", server_default=None)
        op.alter_column("user_prompts", "uses_count", server_default=None)
        return

    prompt_columns = {col["name"] for col in inspector.get_columns("user_prompts")}
    if "preview_url" not in prompt_columns:
        op.add_column("user_prompts", sa.Column("preview_url", sa.Text(), nullable=True))
    if "model" not in prompt_columns:
        op.add_column("user_prompts", sa.Column("model", sa.String(length=64), nullable=True))
    if "tags" not in prompt_columns:
        op.add_column(
            "user_prompts",
            sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        )
    if "likes" not in prompt_columns:
        op.add_column("user_prompts", sa.Column("likes", sa.Integer(), nullable=False, server_default="0"))
    if "is_public" not in prompt_columns:
        op.add_column("user_prompts", sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()))

    op.execute("UPDATE user_prompts SET tags = ARRAY[]::text[] WHERE tags IS NULL")
    op.alter_column("user_prompts", "tags", server_default=None)
    op.alter_column("user_prompts", "likes", server_default=None)
    op.alter_column("user_prompts", "is_public", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    prompt_columns = {col["name"] for col in inspector.get_columns("user_prompts")}
    if "is_public" in prompt_columns:
        op.drop_column("user_prompts", "is_public")
    if "likes" in prompt_columns:
        op.drop_column("user_prompts", "likes")
    if "tags" in prompt_columns:
        op.drop_column("user_prompts", "tags")
    if "model" in prompt_columns:
        op.drop_column("user_prompts", "model")
    if "preview_url" in prompt_columns:
        op.drop_column("user_prompts", "preview_url")

    user_columns = {col["name"] for col in inspector.get_columns("users")}
    if "referrer_l3_id" in user_columns:
        op.drop_constraint("fk_users_referrer_l3_id_users", "users", type_="foreignkey")
        op.drop_column("users", "referrer_l3_id")
