"""Migration 015 — float credits for fractional pricing."""
from __future__ import annotations

revision = "015_float_credits"
down_revision = "014_language_and_stars"

import sqlalchemy as sa
from alembic import op


def upgrade():
    # User credits
    op.alter_column("users", "credits", type_=sa.Float(), existing_type=sa.Integer(), server_default="0")

    # Generation credits_spent
    op.alter_column("generations", "credits_spent", type_=sa.Float(), existing_type=sa.Integer(), server_default="0")

    # ModelCost credits
    op.alter_column("model_costs", "credits", type_=sa.Float(), existing_type=sa.Integer(), nullable=False)

    # PricePlan credits
    op.alter_column("price_plans", "credits", type_=sa.Float(), existing_type=sa.Integer(), nullable=False)


def downgrade():
    op.alter_column("users", "credits", type_=sa.Integer(), existing_type=sa.Float(), server_default="0")
    op.alter_column("generations", "credits_spent", type_=sa.Integer(), existing_type=sa.Float(), server_default="0")
    op.alter_column("model_costs", "credits", type_=sa.Integer(), existing_type=sa.Float(), nullable=False)
    op.alter_column("price_plans", "credits", type_=sa.Integer(), existing_type=sa.Float(), nullable=False)
