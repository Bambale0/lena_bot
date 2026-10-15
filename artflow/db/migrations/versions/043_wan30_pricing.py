"""Add Wan3 and Prime APIX retail rates (credit / billed second).

Revision ID: 043_wan30_pricing
Revises: 042_qwen_routing
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "043_wan30_pricing"
down_revision = "042_qwen_routing"
branch_labels = None
depends_on = None

WAN30_PRICES = (
    ("wan/3-0-video", "🌊 Wan 3.0", (("480p", 6.), ("720p", 12.), ("1080p", 24.))),
    ("wan/3-0-video-prime", "⚡ Wan 3.0 Prime", (("480p", 9.), ("720p", 18.), ("1080p", 36.))),
)


def upgrade() -> None:
    bind = op.get_bind()
    meta = sa.MetaData()
    table = sa.Table("model_costs", meta, autoload_with=bind)
    for model, title, rates in WAN30_PRICES:
        entries = [(model, title, rates[0][1])]
        entries += [(f"{model}__resolution={res}", f"{title} · {res} · за сек", rate) for res, rate in rates]
        for key, label, rate in entries:
            exists = bind.execute(sa.select(table.c.id).where(table.c.model_key == key)).scalar_one_or_none()
            if exists is None:
                bind.execute(table.insert().values(
                    model_key=key, display_name=label, gen_type="video",
                    credits=rate, is_active=True,
                ))


def downgrade() -> None:
    # Preserve past task history and any manually adjusted prices.
    pass
