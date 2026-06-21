"""add ai moderation audit fields to user_prompts

Revision ID: 017_prompt_ai_moderation_audit
Revises: 016_stars_provider
Create Date: 2026-05-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '017_prompt_ai_moderation_audit'
down_revision = '016_stars_provider'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('user_prompts', sa.Column('ai_moderation_decision', sa.String(length=32), nullable=True))
    op.add_column('user_prompts', sa.Column('ai_moderation_risk', sa.String(length=16), nullable=True))
    op.add_column('user_prompts', sa.Column('ai_moderation_reason', sa.String(length=500), nullable=True))
    op.add_column('user_prompts', sa.Column('ai_moderation_recommendation', sa.String(length=500), nullable=True))
    op.add_column('user_prompts', sa.Column('ai_moderation_raw', sa.Text(), nullable=True))
    op.add_column('user_prompts', sa.Column('ai_moderated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('user_prompts', 'ai_moderated_at')
    op.drop_column('user_prompts', 'ai_moderation_raw')
    op.drop_column('user_prompts', 'ai_moderation_recommendation')
    op.drop_column('user_prompts', 'ai_moderation_reason')
    op.drop_column('user_prompts', 'ai_moderation_risk')
    op.drop_column('user_prompts', 'ai_moderation_decision')
