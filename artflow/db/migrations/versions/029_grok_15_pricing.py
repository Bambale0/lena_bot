"""add separate Grok Imagine Video 1.5 pricing

Revision ID: 029_grok_15_pricing
Revises: 028_video_resolution_pricing
Create Date: 2026-07-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "029_grok_15_pricing"
down_revision = "028_video_resolution_pricing"
branch_labels = None
depends_on = None

MODEL_KEY = "grok-imagine-video-1-5-preview"
ROWS = [
    (MODEL_KEY, "🆕 NEW · Grok Imagine Video 1.5", 0.6),
    (f"{MODEL_KEY}__resolution=480p", "🆕 NEW · Grok Imagine Video 1.5 · 480p · за сек", 0.6),
    (f"{MODEL_KEY}__resolution=720p", "🆕 NEW · Grok Imagine Video 1.5 · 720p · за сек", 0.6),
]


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    model_costs = sa.Table("model_costs", metadata, autoload_with=bind)

    for model_key, display_name, credits in ROWS:
        existing_id = bind.execute(
            sa.select(model_costs.c.id).where(model_costs.c.model_key == model_key)
        ).scalar_one_or_none()
        values = {
            "model_key": model_key,
            "display_name": display_name,
            "gen_type": "video",
            "credits": float(credits),
            "is_active": True,
        }
        if existing_id is None:
            bind.execute(model_costs.insert().values(**values))
        else:
            bind.execute(
                model_costs.update()
                .where(model_costs.c.id == existing_id)
                .values(**values)
            )


def downgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    model_costs = sa.Table("model_costs", metadata, autoload_with=bind)
    bind.execute(model_costs.delete().where(model_costs.c.model_key.in_([row[0] for row in ROWS])))
