# db/seed.py
"""
Автозаполнение начальных данных при старте.
Вызывается из run_polling.py и main.py (lifespan) после create_all.
Идемпотентно — не дублирует записи.
"""
from __future__ import annotations

import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import GenerationType, ModelCost, PricePlan, UserPrompt
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

# ── Стартовые тарифы ──────────────────────────────────────────────────────────
DEFAULT_PRICE_PLANS = [
    {"key": "credits_100",  "label": "100 кредитов",  "credits": 100,  "price_rub": 199.0,  "sort_order": 1},
    {"key": "credits_300",  "label": "300 кредитов",  "credits": 300,  "price_rub": 499.0,  "sort_order": 2},
    {"key": "credits_1000", "label": "1000 кредитов", "credits": 1000, "price_rub": 1490.0, "sort_order": 3},
]

# ── Стоимость моделей ─────────────────────────────────────────────────────────
DEFAULT_MODEL_COSTS = [
    # Изображения
    {"model_key": "seedream-4.5",    "display_name": "🌸 Seedream 4.5",               "gen_type": GenerationType.image, "credits": 2},
    {"model_key": "nano-banano-pro", "display_name": "🍌 Nano Banano Pro (Gemini 3 Pro)",   "gen_type": GenerationType.image, "credits": 4},
    {"model_key": "nano-banano-2",   "display_name": "🍌 Nano Banano 2 (Gemini 3.1 Flash)", "gen_type": GenerationType.image, "credits": 2},
    {"model_key": "wan-2.7",         "display_name": "🌊 WAN 2.7",                    "gen_type": GenerationType.image, "credits": 3},
    {"model_key": "gpt-image-1",     "display_name": "🤖 GPT Imagine 2",              "gen_type": GenerationType.image, "credits": 4},
    # Видео
    {"model_key": "grok-video",      "display_name": "🐦 Grok Video",        "gen_type": GenerationType.video, "credits": 40},
    {"model_key": "kling-3.0",       "display_name": "⚡ Kling 3.0",         "gen_type": GenerationType.video, "credits": 30},
    {"model_key": "kling-2.6-motion","display_name": "🎭 Kling 2.6 Motion",  "gen_type": GenerationType.video, "credits": 35},
    # Grok Imagine Video (новый endpoint)
    {"model_key": "grok-imagine-video",              "display_name": "🐦 Grok Imagine Video", "gen_type": GenerationType.video, "credits": 45},
    # Seedance 2.0
    {"model_key": "doubao-seedance-2-0",             "display_name": "🌱 Seedance 2.0",       "gen_type": GenerationType.video, "credits": 30},
    # Veo 3.1 Pro
    {"model_key": "veo3.1-pro",                      "display_name": "🎬 Veo 3.1 Pro",        "gen_type": GenerationType.video, "credits": 50},
    # HappyHorse
    {"model_key": "happyhorse-1.0-text-to-video",    "display_name": "🐎 HappyHorse T2V",     "gen_type": GenerationType.video, "credits": 25},
    {"model_key": "happyhorse-1.0-image-to-video",   "display_name": "🐎 HappyHorse I2V",     "gen_type": GenerationType.video, "credits": 30},
    # Wan 2.7 Image Pro (kie.ai)
    {"model_key": "wan-2.7-pro",                     "display_name": "🌊 WAN 2.7 Image Pro",  "gen_type": GenerationType.image, "credits": 5},
    # Midjourney
    {"model_key": "midjourney-imagine",  "display_name": "🖌️ MJ Imagine",  "gen_type": GenerationType.image, "credits": 10},
    {"model_key": "midjourney-action",   "display_name": "🖌️ MJ Action",   "gen_type": GenerationType.image, "credits": 3},
    {"model_key": "midjourney-blend",    "display_name": "🖼️ MJ Blend",    "gen_type": GenerationType.image, "credits": 12},
    {"model_key": "midjourney-describe", "display_name": "🔍 MJ Describe",  "gen_type": GenerationType.image, "credits": 5},
    {"model_key": "midjourney-video",    "display_name": "🎞️ MJ Video",    "gen_type": GenerationType.video,  "credits": 15},
]


async def run_seed() -> None:
    """Вставляет данные только если таблицы пустые."""
    async with AsyncSessionLocal() as session:
        await _seed_price_plans(session)
        await _seed_model_costs(session)


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
