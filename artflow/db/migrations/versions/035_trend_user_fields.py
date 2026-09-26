"""Store curated trend personalization schema on user prompts.

Revision ID: 035_trend_user_fields
Revises: 034_user_image_model_unlimited
Create Date: 2026-09-26
"""

from alembic import op
import sqlalchemy as sa


revision = "035_trend_user_fields"
down_revision = "034_user_image_model_unlimited"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable is intentional: existing prompts keep NULL so legacy {{Field}}
    # placeholders can still be auto-discovered. New/edited trends persist an
    # explicit list, including [] when personalization is disabled.
    op.add_column(
        "user_prompts",
        sa.Column("trend_user_fields", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_prompts", "trend_user_fields")
