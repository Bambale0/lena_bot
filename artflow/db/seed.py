# db/seed.py
"""
Автозаполнение начальных данных при старте.
Вызывается из run_polling.py и main.py после применения миграций.
Идемпотентно — не дублирует записи.
"""
from __future__ import annotations

import logging

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.model_pricing import duration_label, pricing_variant_key, quality_label, resolution_label
from db.models import GenerationType, ModelCost, PricePlan, UserPrompt
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

# ── Стартовые тарифы ──────────────────────────────────────────────────────────
DEFAULT_PRICE_PLANS = [
    {"key": "credits_100",  "label": "100 💋",  "credits": 100,  "price_rub": 199.0,  "sort_order": 1},
    {"key": "credits_300",  "label": "300 💋",  "credits": 300,  "price_rub": 499.0,  "sort_order": 2},
    {"key": "credits_1000", "label": "1000 💋", "credits": 1000, "price_rub": 1490.0, "sort_order": 3},
]

# ── Стоимость моделей ─────────────────────────────────────────────────────────
DEFAULT_MODEL_COSTS = [
    # ── Изображения (KIE.AI) ──────────────────────────────────────────────────
    {"model_key": "seedream/4.5-text-to-image", "display_name": "🌸 Seedream 4.5",        "gen_type": GenerationType.image, "credits": 3},
    {"model_key": "seedream/4.5-edit",          "display_name": "🌸 Seedream 4.5 Edit",   "gen_type": GenerationType.image, "credits": 3},
    {"model_key": "grok-imagine/text-to-image", "display_name": "⚡ Grok Imagine T2I",    "gen_type": GenerationType.image, "credits": 3},
    {"model_key": "grok-imagine/image-to-image","display_name": "⚡ Grok Imagine I2I",    "gen_type": GenerationType.image, "credits": 3},
    {"model_key": "wan/2-7-image-pro",          "display_name": "🌊 WAN 2.7 Image Pro",   "gen_type": GenerationType.image, "credits": 5},
    {"model_key": "google/nano-banana",         "display_name": "🍌 Nano Banana",         "gen_type": GenerationType.image, "credits": 2},
    {"model_key": "nano-banana-2",              "display_name": "🍌 Nano Banana 2",        "gen_type": GenerationType.image, "credits": 3},
    {"model_key": "nano-banana-pro",            "display_name": "🍌 Nano Banana Pro",      "gen_type": GenerationType.image, "credits": 4},
    {"model_key": "qwen/text-to-image",         "display_name": "🟣 Qwen T2I",             "gen_type": GenerationType.image, "credits": 3},
    {"model_key": "qwen/image-to-image",        "display_name": "🟣 Qwen I2I",             "gen_type": GenerationType.image, "credits": 3},
    {"model_key": "qwen/image-edit",            "display_name": "🟣 Qwen Edit",            "gen_type": GenerationType.image, "credits": 3},
    {"model_key": "qwen2/text-to-image",        "display_name": "🟣 Qwen2 T2I",            "gen_type": GenerationType.image, "credits": 4},
    {"model_key": "qwen2/image-edit",           "display_name": "🟣 Qwen2 Edit",           "gen_type": GenerationType.image, "credits": 4},
    # ── Видео (KIE.AI) ────────────────────────────────────────────────────────
    {"model_key": "kling-2.6/text-to-video",   "display_name": "⚙️ Kling 2.6 T2V",       "gen_type": GenerationType.video, "credits": 30},
    {"model_key": "kling-2.6/image-to-video",  "display_name": "⚙️ Kling 2.6 I2V",       "gen_type": GenerationType.video, "credits": 35},
    {"model_key": "kling-2.6/motion-control",  "display_name": "🕺 Kling 2.6 Motion",     "gen_type": GenerationType.video, "credits": 40},
    {"model_key": "kling-3.0/video",           "display_name": "⚡ Kling 3.0",             "gen_type": GenerationType.video, "credits": 40},
    {"model_key": "kling-3.0/motion-control",  "display_name": "🕺 Kling 3.0 Motion",     "gen_type": GenerationType.video, "credits": 50},
    {"model_key": "wan/2-7-text-to-video",     "display_name": "🌊 WAN 2.7 T2V",          "gen_type": GenerationType.video, "credits": 25},
    {"model_key": "wan/2-7-image-to-video",    "display_name": "🌊 WAN 2.7 I2V",          "gen_type": GenerationType.video, "credits": 30},
    {"model_key": "bytedance/seedance-2",      "display_name": "🌱 Seedance 2",            "gen_type": GenerationType.video, "credits": 35},
    {"model_key": "bytedance/seedance-2-fast", "display_name": "🌱 Seedance 2 Fast",       "gen_type": GenerationType.video, "credits": 25},
    {"model_key": "grok-imagine/text-to-video","display_name": "⚡ Grok T2V",              "gen_type": GenerationType.video, "credits": 35},
    {"model_key": "grok-imagine/image-to-video","display_name":"⚡ Grok I2V",              "gen_type": GenerationType.video, "credits": 35},
    {"model_key": "happyhorse/text-to-video",  "display_name": "🐎 HappyHorse T2V",        "gen_type": GenerationType.video, "credits": 25},
    {"model_key": "happyhorse/image-to-video", "display_name": "🐎 HappyHorse I2V",        "gen_type": GenerationType.video, "credits": 30},
    {"model_key": "veo3_fast",                 "display_name": "🎬 Veo 3 Fast",            "gen_type": GenerationType.video, "credits": 50},
    {"model_key": "veo3",                      "display_name": "🎬 Veo 3",                 "gen_type": GenerationType.video, "credits": 70},
    {"model_key": "veo3_lite",                 "display_name": "🎬 Veo 3 Lite",            "gen_type": GenerationType.video, "credits": 35},
    # ── GPT Image 2 ─────────────────────────────────────────────────────────
    {"model_key": "gpt-image-2-text-to-image",   "display_name": "🤖 GPT Image 2 T2I",                 "gen_type": GenerationType.image, "credits": 4},
    {"model_key": "gpt-image-2-image-to-image", "display_name": "🤖 GPT Image 2 I2I",                 "gen_type": GenerationType.image, "credits": 4},
    # ── Музыка ────────────────────────────────────────────────────────────────
    {"model_key": "suno/v4.5",                  "display_name": "🎵 Suno v4.5",                        "gen_type": GenerationType.music, "credits": 20},
    # ── Midjourney ────────────────────────────────────────────────────────────
    {"model_key": "midjourney-imagine",  "display_name": "🖌️ MJ Imagine",  "gen_type": GenerationType.image, "credits": 10},
    {"model_key": "midjourney-action",   "display_name": "🖌️ MJ Action",   "gen_type": GenerationType.image, "credits": 3},
    {"model_key": "midjourney-blend",    "display_name": "🖼️ MJ Blend",    "gen_type": GenerationType.image, "credits": 12},
    {"model_key": "midjourney-describe", "display_name": "🔍 MJ Describe",  "gen_type": GenerationType.image, "credits": 5},
    {"model_key": "midjourney-video",    "display_name": "🎞️ MJ Video",    "gen_type": GenerationType.video,  "credits": 15},
]


_IMAGE_VARIANT_COSTS = [
    ("seedream/4.5-text-to-image", "🌸 Seedream 4.5", [("basic", 3), ("high", 4)]),
    ("seedream/4.5-edit", "🌸 Seedream 4.5 Edit", [("basic", 3), ("high", 4)]),
    ("wan/2-7-image-pro", "🌊 WAN 2.7 Image Pro", [("1K", 4), ("2K", 5), ("4K", 6)]),
    ("nano-banana-2", "🍌 Nano Banana 2", [("2K", 3), ("4K", 4)]),
    ("nano-banana-pro", "🍌 Nano Banana Pro", [("2K", 4), ("4K", 5)]),
]

# ─── Per-second pricing for video models ─────────────────────────────────────
# Format: (model_key, display_name, resolutions, credits_per_second_per_resolution)
# Base model entry uses the cheapest resolution's per-second rate as default.
_KLING_VIDEO_VARIANTS = [
    (
        "kling-2.6/text-to-video",
        "⚙️ Kling 2.6 T2V",
        ["720p", "1080p"],
        {"720p": 5, "1080p": 7},
    ),
    (
        "kling-2.6/image-to-video",
        "⚙️ Kling 2.6 I2V",
        ["720p", "1080p"],
        {"720p": 6, "1080p": 8},
    ),
    (
        "kling-2.6/motion-control",
        "🕺 Kling 2.6 Motion",
        ["720p", "1080p"],
        {"720p": 7, "1080p": 9},
    ),
    (
        "kling-3.0/video",
        "⚡ Kling 3.0",
        ["2K", "4K"],
        {"2K": 8, "4K": 10},
    ),
    (
        "kling-3.0/motion-control",
        "🕺 Kling 3.0 Motion",
        ["2K", "4K"],
        {"2K": 9, "4K": 11},
    ),
]


def _build_variant_model_costs() -> list[dict]:
    records: list[dict] = []

    for model_key, display_name, tiers in _IMAGE_VARIANT_COSTS:
        for quality, credits in tiers:
            records.append(
                {
                    "model_key": pricing_variant_key(model_key, quality=quality),
                    "display_name": f"{display_name} · {quality_label(quality)}",
                    "gen_type": GenerationType.image,
                    "credits": credits,
                }
            )

    for model_key, display_name, resolutions, prices_per_sec in _KLING_VIDEO_VARIANTS:
        for resolution in resolutions:
            records.append(
                {
                    "model_key": pricing_variant_key(model_key, resolution=resolution),
                    "display_name": f"{display_name} · {resolution_label(resolution)} · за сек",
                    "gen_type": GenerationType.video,
                    "credits": prices_per_sec[resolution],
                }
            )

    return records


DEFAULT_MODEL_COSTS.extend(_build_variant_model_costs())

LEGACY_MODEL_ALIASES_TO_DISABLE = {
    "google/nano-banana",
    "seedream-4.5",
    "nano-banano-2",
    "nano-banano-pro",
    "wan-2.7",
    "wan-2.7-pro",
    "gpt-image-1",
    # Old 1K quality variants for nano banana
    "nano-banana-2__quality=1K",
    "nano-banana-pro__quality=1K",
    # Old duration-based Kling 3.0 variants (replaced by per-second / resolution-only)
    "kling-3.0/video__duration=3__resolution=std",
    "kling-3.0/video__duration=3__resolution=pro",
    "kling-3.0/video__duration=3__resolution=4K",
    "kling-3.0/video__duration=5__resolution=std",
    "kling-3.0/video__duration=5__resolution=pro",
    "kling-3.0/video__duration=5__resolution=4K",
    "kling-3.0/video__duration=10__resolution=std",
    "kling-3.0/video__duration=10__resolution=pro",
    "kling-3.0/video__duration=10__resolution=4K",
    "kling-3.0/video__resolution=std",
    "kling-3.0/video__resolution=pro",
    # Old duration-only Kling 2.6 variants
    "kling-2.6/text-to-video__duration=5",
    "kling-2.6/text-to-video__duration=10",
    "kling-2.6/image-to-video__duration=5",
    "kling-2.6/image-to-video__duration=10",
    # Old motion control resolution variants
    "kling-2.6/motion-control__resolution=720p",
    "kling-2.6/motion-control__resolution=1080p",
    "kling-3.0/motion-control__resolution=720p",
    "kling-3.0/motion-control__resolution=1080p",
}


async def run_seed() -> None:
    """Вставляет данные только если таблицы пустые."""
    async with AsyncSessionLocal() as session:
        await _seed_price_plans(session)
        await _seed_model_costs(session)
        await _disable_legacy_model_aliases(session)


async def _seed_price_plans(session: AsyncSession) -> None:
    count = (await session.execute(select(func.count()).select_from(PricePlan))).scalar_one()
    if count > 0:
        return

    logger.info("Seed: вставляем %d тарифов...", len(DEFAULT_PRICE_PLANS))
    for data in DEFAULT_PRICE_PLANS:
        session.add(PricePlan(
            key=data["key"],
            label=data["label"],
            credits=data["credits"],
            price_rub=data["price_rub"],
            sort_order=data["sort_order"],
            is_active=True,
        ))
    await session.commit()
    logger.info("Seed: тарифы вставлены ✓")


async def _seed_model_costs(session: AsyncSession) -> None:
    """Upsert: добавляет только отсутствующие модели (идемпотентно)."""
    existing_keys: set[str] = set(
        (await session.execute(select(ModelCost.model_key))).scalars().all()
    )
    new_models = [d for d in DEFAULT_MODEL_COSTS if d["model_key"] not in existing_keys]

    if not new_models:
        return

    logger.info("Seed: вставляем %d новых моделей...", len(new_models))
    for data in new_models:
        session.add(ModelCost(
            model_key=data["model_key"],
            display_name=data["display_name"],
            gen_type=data["gen_type"],
            credits=data["credits"],
            is_active=True,
        ))
    await session.commit()
    logger.info("Seed: модели вставлены ✓")


async def _disable_legacy_model_aliases(session: AsyncSession) -> None:
    result = await session.execute(
        update(ModelCost)
        .where(ModelCost.model_key.in_(LEGACY_MODEL_ALIASES_TO_DISABLE), ModelCost.is_active == True)
        .values(is_active=False)
        .returning(ModelCost.model_key)
    )
    disabled = list(result.scalars().all())
    if not disabled:
        await session.rollback()
        return

    await session.commit()
    logger.info("Seed: отключены legacy model aliases: %s", ", ".join(sorted(disabled)))
