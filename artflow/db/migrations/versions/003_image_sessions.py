"""add image sessions

Revision ID: 003_image_sessions
Revises: 002
Create Date: 2026-05-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


revision = "003_image_sessions"
down_revision = "002"
branch_labels = None
depends_on = None


image_session_status = postgresql.ENUM(
    "active",
    "archived",
    name="imagesessionstatus",
    create_type=False,
)
image_generation_action = postgresql.ENUM(
    "initial",
    "remix",
    "repeat",
    "reference_update",
    "animate",
    name="imagegenerationaction",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    image_session_status.create(bind, checkfirst=True)
    image_generation_action.create(bind, checkfirst=True)

    if not inspector.has_table("image_sessions"):
        op.create_table(
            "image_sessions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("model", sa.String(length=64), nullable=False),
            sa.Column("mode", sa.String(length=32), nullable=False, server_default="text"),
            sa.Column("aspect_ratio", sa.String(length=32), nullable=True),
            sa.Column("quality", sa.String(length=32), nullable=False, server_default="basic"),
            sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("base_prompt", sa.Text(), nullable=True),
            sa.Column("reference_file_id", sa.Text(), nullable=True),
            sa.Column("last_result_url", sa.Text(), nullable=True),
            sa.Column("last_generation_id", sa.Integer(), nullable=True),
            sa.Column("status", image_session_status, nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    image_session_indexes = {idx["name"] for idx in inspector.get_indexes("image_sessions")}
    if "ix_image_sessions_user_id" not in image_session_indexes:
        op.create_index("ix_image_sessions_user_id", "image_sessions", ["user_id"])
    if "ix_image_sessions_status" not in image_session_indexes:
        op.create_index("ix_image_sessions_status", "image_sessions", ["status"])

    generation_columns = {col["name"] for col in inspector.get_columns("generations")}
    if "image_session_id" not in generation_columns:
        op.add_column("generations", sa.Column("image_session_id", sa.Integer(), nullable=True))
    if "parent_generation_id" not in generation_columns:
        op.add_column("generations", sa.Column("parent_generation_id", sa.Integer(), nullable=True))
    if "action_type" not in generation_columns:
        op.add_column("generations", sa.Column("action_type", image_generation_action, nullable=True))

    generation_indexes = {idx["name"] for idx in inspector.get_indexes("generations")}
    if "ix_generations_image_session_id" not in generation_indexes:
        op.create_index("ix_generations_image_session_id", "generations", ["image_session_id"])
    if "ix_generations_task_id" not in generation_indexes:
        op.create_index("ix_generations_task_id", "generations", ["task_id"])

    generation_fks = {fk["name"] for fk in inspector.get_foreign_keys("generations")}
    if "fk_generations_image_session_id_image_sessions" not in generation_fks:
        op.create_foreign_key(
            "fk_generations_image_session_id_image_sessions",
            "generations",
            "image_sessions",
            ["image_session_id"],
            ["id"],
        )
    if "fk_generations_parent_generation_id_generations" not in generation_fks:
        op.create_foreign_key(
            "fk_generations_parent_generation_id_generations",
            "generations",
            "generations",
            ["parent_generation_id"],
            ["id"],
        )


def downgrade() -> None:
    op.drop_constraint("fk_generations_parent_generation_id_generations", "generations", type_="foreignkey")
    op.drop_constraint("fk_generations_image_session_id_image_sessions", "generations", type_="foreignkey")
    op.drop_index("ix_generations_task_id", table_name="generations")
    op.drop_index("ix_generations_image_session_id", table_name="generations")
    op.drop_column("generations", "action_type")
    op.drop_column("generations", "parent_generation_id")
    op.drop_column("generations", "image_session_id")

    op.drop_index("ix_image_sessions_status", table_name="image_sessions")
    op.drop_index("ix_image_sessions_user_id", table_name="image_sessions")
    op.drop_table("image_sessions")

    bind = op.get_bind()
    image_generation_action.drop(bind, checkfirst=True)
    image_session_status.drop(bind, checkfirst=True)
