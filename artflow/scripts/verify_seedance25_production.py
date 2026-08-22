#!/usr/bin/env python3
"""Fail deployment unless production can render Seedance 2.5 in feed video repeat.

This check deliberately runs inside the freshly started app container. It proves
three things that unit tests and a generic HTTP health endpoint cannot prove:

1. the runtime repository layer exposes the Seedance 2.5 ModelCost;
2. the exact Telegram ``i2v`` keyboard used by ``feed:use`` renders its button;
3. the configured bot token's Telegram webhook points at this deployment URL.

No secrets are printed.
"""
from __future__ import annotations

import asyncio

from aiogram import Bot
from sqlalchemy import select

from api.seedance25_adapter import MODEL_KEY, install_seedance25_provider_support
from api.seedance25_product_surface import install_seedance25_product_surface
from bot.keyboards.models import video_models_kb
from core.config import settings
from db import repository as repo
from db.models import ModelCost
from db.session import AsyncSessionLocal

EXPECTED_CALLBACK = f"vid_model:{MODEL_KEY}"


def _keyboard_snapshot(markup) -> list[tuple[str, str | None]]:
    return [
        (button.text, button.callback_data)
        for row in markup.inline_keyboard
        for button in row
    ]


async def _verify_runtime_keyboard() -> None:
    # Keep this explicit so the verification remains valid even if bootstrap
    # import ordering changes in the future.
    install_seedance25_provider_support()
    install_seedance25_product_surface()

    async with AsyncSessionLocal() as session:
        raw_rows = list(
            (
                await session.execute(
                    select(ModelCost).where(ModelCost.model_key.like(f"{MODEL_KEY}%"))
                )
            )
            .scalars()
            .all()
        )
        print(
            "[seedance25-proof] db_rows="
            + repr(
                [
                    {
                        "model_key": row.model_key,
                        "display_name": row.display_name,
                        "credits": float(row.credits),
                        "is_active": bool(row.is_active),
                    }
                    for row in raw_rows
                ]
            )
        )

        model_costs = list(await repo.get_all_model_costs(session))
        visible = [row for row in model_costs if getattr(row, "model_key", None) == MODEL_KEY]
        if not visible:
            raise RuntimeError(
                f"runtime repository does not expose required model {MODEL_KEY}"
            )

        markup = video_models_kb(model_costs, "i2v")
        buttons = _keyboard_snapshot(markup)
        callbacks = [callback for _, callback in buttons if callback]
        texts = [text for text, _ in buttons]

        print(
            "[seedance25-proof] runtime_model="
            + repr(
                [
                    {
                        "model_key": getattr(row, "model_key", None),
                        "display_name": getattr(row, "display_name", None),
                        "credits": float(getattr(row, "credits", 0)),
                        "is_active": bool(getattr(row, "is_active", True)),
                    }
                    for row in visible
                ]
            )
        )
        print(f"[seedance25-proof] i2v_buttons={texts!r}")

        if callbacks.count(EXPECTED_CALLBACK) != 1:
            raise RuntimeError(
                "feed repeat keyboard must expose exactly one Seedance 2.5 button: "
                f"expected={EXPECTED_CALLBACK!r}, callbacks={callbacks!r}"
            )


async def _verify_telegram_webhook() -> None:
    expected_url = f"{settings.WEBHOOK_URL}{settings.WEBHOOK_PATH}"
    bot = Bot(token=settings.BOT_TOKEN)
    try:
        me = await bot.get_me()
        webhook = await bot.get_webhook_info()
    finally:
        await bot.session.close()

    print(
        "[seedance25-proof] telegram="
        + repr(
            {
                "username": me.username,
                "webhook_url": webhook.url,
                "expected_url": expected_url,
                "pending_updates": webhook.pending_update_count,
            }
        )
    )
    if webhook.url != expected_url:
        raise RuntimeError(
            "Telegram webhook for the configured production bot points elsewhere: "
            f"actual={webhook.url!r}, expected={expected_url!r}"
        )


async def main() -> None:
    await _verify_runtime_keyboard()
    await _verify_telegram_webhook()
    print("[seedance25-proof] OK: production feed repeat renders Seedance 2.5")


if __name__ == "__main__":
    asyncio.run(main())
