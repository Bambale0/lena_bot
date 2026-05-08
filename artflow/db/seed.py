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
    # ── Midjourney ────────────────────────────────────────────────────────────
    {"model_key": "midjourney-imagine",  "display_name": "🖌️ MJ Imagine",  "gen_type": GenerationType.image, "credits": 10},
    {"model_key": "midjourney-action",   "display_name": "🖌️ MJ Action",   "gen_type": GenerationType.image, "credits": 3},
    {"model_key": "midjourney-blend",    "display_name": "🖼️ MJ Blend",    "gen_type": GenerationType.image, "credits": 12},
    {"model_key": "midjourney-describe", "display_name": "🔍 MJ Describe",  "gen_type": GenerationType.image, "credits": 5},
    {"model_key": "midjourney-video",    "display_name": "🎞️ MJ Video",    "gen_type": GenerationType.video,  "credits": 15},
]

LEGACY_MODEL_ALIASES_TO_DISABLE = {
    "google/nano-banana",
    "seedream-4.5",
    "nano-banano-2",
    "nano-banano-pro",
    "wan-2.7",
    "wan-2.7-pro",
    "gpt-image-1",
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
