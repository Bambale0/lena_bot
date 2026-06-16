"""add video resolution pricing variants

Revision ID: 028_video_resolution_pricing
Revises: 027_generation_input_params
Create Date: 2026-06-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "028_video_resolution_pricing"
down_revision = "027_generation_input_params"
branch_labels = None
depends_on = None


VIDEO_RESOLUTION_VARIANTS = [
    ("kling-2.6/text-to-video__resolution=720p", "⚙️ Kling 2.6 · 720p · за сек", 5),
    ("kling-2.6/text-to-video__resolution=1080p", "⚙️ Kling 2.6 · 1080p · за сек", 7),
    ("kling-2.6/image-to-video__resolution=720p", "⚙️ Kling 2.6 Animate · 720p · за сек", 6),
    ("kling-2.6/image-to-video__resolution=1080p", "⚙️ Kling 2.6 Animate · 1080p · за сек", 8),
    ("kling-2.6/motion-control__resolution=720p", "🕺 Kling 2.6 Motion · 720p · за сек", 7),
    ("kling-2.6/motion-control__resolution=1080p", "🕺 Kling 2.6 Motion · 1080p · за сек", 9),
    ("kling-3.0/video__resolution=std", "⚡ Kling 3.0 · Std · за сек", 6),
    ("kling-3.0/video__resolution=pro", "⚡ Kling 3.0 · Pro · за сек", 8),
    ("kling-3.0/video__resolution=4K", "⚡ Kling 3.0 · 4K · за сек", 10),
    ("kling-3.0/motion-control__resolution=720p", "🕺 Kling 3.0 Motion · 720p · за сек", 9),
    ("kling-3.0/motion-control__resolution=1080p", "🕺 Kling 3.0 Motion · 1080p · за сек", 11),
    ("wan/2-7-text-to-video__resolution=720p", "🌊 WAN Video · 720p · за сек", 20),
    ("wan/2-7-text-to-video__resolution=1080p", "🌊 WAN Video · 1080p · за сек", 25),
    ("wan/2-7-image-to-video__resolution=720p", "🌊 WAN Animate · 720p · за сек", 24),
    ("wan/2-7-image-to-video__resolution=1080p", "🌊 WAN Animate · 1080p · за сек", 30),
    ("bytedance/seedance-2__resolution=480p", "🌱 Seedance 2 · 480p · за сек", 5),
    ("bytedance/seedance-2__resolution=720p", "🌱 Seedance 2 · 720p · за сек", 7),
    ("bytedance/seedance-2__resolution=1080p", "🌱 Seedance 2 · 1080p · за сек", 9),
    ("bytedance/seedance-2-fast__resolution=480p", "🌱 Seedance 2 Fast · 480p · за сек", 4),
    ("bytedance/seedance-2-fast__resolution=720p", "🌱 Seedance 2 Fast · 720p · за сек", 5),
    ("grok-imagine/text-to-video__resolution=480p", "⚡ Grok Video · 480p · за сек", 35),
    ("grok-imagine/text-to-video__resolution=720p", "⚡ Grok Video · 720p · за сек", 45),
    ("grok-imagine/image-to-video__resolution=480p", "⚡ Grok Animate · 480p · за сек", 35),
    ("grok-imagine/image-to-video__resolution=720p", "⚡ Grok Animate · 720p · за сек", 45),
    ("happyhorse/text-to-video__resolution=720p", "🐎 HappyHorse Video · 720p · за сек", 20),
    ("happyhorse/text-to-video__resolution=1080p", "🐎 HappyHorse Video · 1080p · за сек", 25),
    ("happyhorse/image-to-video__resolution=720p", "🐎 HappyHorse Animate · 720p · за сек", 25),
    ("happyhorse/image-to-video__resolution=1080p", "🐎 HappyHorse Animate · 1080p · за сек", 30),
    ("veo3_fast__resolution=720p", "🎬 Veo 3 Fast · 720p · за сек", 40),
    ("veo3_fast__resolution=1080p", "🎬 Veo 3 Fast · 1080p · за сек", 50),
    ("veo3__resolution=720p", "🎬 Veo 3 · 720p · за сек", 55),
    ("veo3__resolution=1080p", "🎬 Veo 3 · 1080p · за сек", 70),
    ("veo3_lite__resolution=720p", "🎬 Veo 3 Lite · 720p · за сек", 28),
    ("veo3_lite__resolution=1080p", "🎬 Veo 3 Lite · 1080p · за сек", 35),
]

VIDEO_BASE_RATES = [
    ("kling-2.6/text-to-video", "⚙️ Kling 2.6", 5),
    ("kling-2.6/image-to-video", "⚙️ Kling 2.6 Animate", 6),
    ("kling-2.6/motion-control", "🕺 Kling 2.6 Motion", 7),
    ("kling-3.0/video", "⚡ Kling 3.0", 6),
    ("kling-3.0/motion-control", "🕺 Kling 3.0 Motion", 9),
    ("wan/2-7-text-to-video", "🌊 WAN Video", 20),
    ("wan/2-7-image-to-video", "🌊 WAN Animate", 24),
    ("bytedance/seedance-2", "🌱 Seedance 2", 5),
    ("bytedance/seedance-2-fast", "🌱 Seedance 2 Fast", 4),
    ("grok-imagine/text-to-video", "⚡ Grok Video", 35),
    ("grok-imagine/image-to-video", "⚡ Grok Animate", 35),
    ("happyhorse/text-to-video", "🐎 HappyHorse Video", 20),
    ("happyhorse/image-to-video", "🐎 HappyHorse Animate", 25),
    ("veo3_fast", "🎬 Veo 3 Fast", 40),
    ("veo3", "🎬 Veo 3", 55),
    ("veo3_lite", "🎬 Veo 3 Lite", 28),
]


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    model_costs = sa.Table("model_costs", metadata, autoload_with=bind)

    for model_key, display_name, credits in [*VIDEO_BASE_RATES, *VIDEO_RESOLUTION_VARIANTS]:
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
    pass
