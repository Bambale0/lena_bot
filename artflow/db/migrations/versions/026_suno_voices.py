"""add suno custom voices

Revision ID: 026_suno_voices
Revises: 025_feed_remix_payouts
Create Date: 2026-06-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "026_suno_voices"
down_revision = "025_feed_remix_payouts"
branch_labels = None
depends_on = None


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {index["name"] for index in inspector.get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "suno_voices" not in inspector.get_table_names():
        op.create_table(
            "suno_voices",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("style", sa.String(length=256), nullable=True),
            sa.Column("source_audio_url", sa.Text(), nullable=False),
            sa.Column("verify_audio_url", sa.Text(), nullable=True),
            sa.Column("validate_task_id", sa.String(length=256), nullable=True),
            sa.Column("voice_task_id", sa.String(length=256), nullable=True),
            sa.Column("voice_id", sa.String(length=256), nullable=True),
            sa.Column("validate_phrase", sa.Text(), nullable=True),
            sa.Column("language", sa.String(length=8), nullable=False, server_default="en"),
            sa.Column("vocal_start_s", sa.Float(), nullable=False, server_default="0"),
            sa.Column("vocal_end_s", sa.Float(), nullable=False, server_default="10"),
            sa.Column("singer_skill_level", sa.String(length=32), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="validating"),
            sa.Column("error_msg", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    _create_index_if_missing("ix_suno_voices_user_id", "suno_voices", ["user_id"])
    _create_index_if_missing("ix_suno_voices_validate_task_id", "suno_voices", ["validate_task_id"])
    _create_index_if_missing("ix_suno_voices_voice_task_id", "suno_voices", ["voice_task_id"])
    _create_index_if_missing("ix_suno_voices_voice_id", "suno_voices", ["voice_id"])
    _create_index_if_missing("ix_suno_voices_status", "suno_voices", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "suno_voices" in inspector.get_table_names():
        op.drop_table("suno_voices")
