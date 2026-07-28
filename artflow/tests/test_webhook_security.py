from __future__ import annotations

import asyncio

import pytest
from aiogram.exceptions import TelegramForbiddenError
from httpx import ASGITransport, AsyncClient

import main
from main import app


@pytest.mark.asyncio
async def test_midjourney_webhook_requires_secret_in_production(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "ENV", "production")
    monkeypatch.setattr(main.settings, "MIDJOURNEY_WEBHOOK_SECRET", "")
    monkeypatch.setattr(main.settings, "WEBHOOK_SECRET", "")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(main.settings.MIDJOURNEY_WEBHOOK_PATH, json={"taskId": "mj-1"})

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_midjourney_webhook_rejects_wrong_secret(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "ENV", "production")
    monkeypatch.setattr(main.settings, "MIDJOURNEY_WEBHOOK_SECRET", "expected-secret")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"{main.settings.MIDJOURNEY_WEBHOOK_PATH}?secret=wrong",
            json={"taskId": "mj-1"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_telegram_webhook_acks_blocked_user_updates(monkeypatch) -> None:
    class ForbiddenDispatcher:
        async def feed_update(self, bot, update) -> None:
            raise TelegramForbiddenError(
                method=object(),
                message="Forbidden: bot was blocked by the user",
            )

    monkeypatch.setattr(main, "dp", ForbiddenDispatcher())
    monkeypatch.setattr(main, "bot", object())

    update = {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "date": 1779638390,
            "chat": {"id": 123, "type": "private", "first_name": "Test"},
            "from": {"id": 123, "is_bot": False, "first_name": "Test"},
            "text": "/start",
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            main.settings.WEBHOOK_PATH,
            headers={"X-Telegram-Bot-Api-Secret-Token": main.settings.WEBHOOK_SECRET},
            json=update,
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_telegram_webhook_rejects_spoofed_telegram_ip_without_secret(monkeypatch) -> None:
    class CountingDispatcher:
        def __init__(self) -> None:
            self.calls = 0

        async def feed_update(self, bot, update) -> None:
            self.calls += 1

    dispatcher = CountingDispatcher()
    monkeypatch.setattr(main, "dp", dispatcher)
    monkeypatch.setattr(main, "bot", object())
    monkeypatch.setattr(main, "redis_client", None)
    monkeypatch.setattr(main.settings, "WEBHOOK_SECRET", "expected-secret")
    main._recent_telegram_updates.clear()

    update = {
        "update_id": 987655,
        "message": {
            "message_id": 10,
            "date": 1779638390,
            "chat": {"id": 123, "type": "private", "first_name": "Test"},
            "from": {"id": 123, "is_bot": False, "first_name": "Test"},
            "text": "/start",
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            main.settings.WEBHOOK_PATH,
            headers={"X-Forwarded-For": "91.108.5.111"},
            json=update,
        )

    await asyncio.sleep(0)
    assert response.status_code == 403
    assert dispatcher.calls == 0


@pytest.mark.asyncio
async def test_telegram_webhook_requires_secret_in_production(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "ENV", "production")
    monkeypatch.setattr(main.settings, "WEBHOOK_SECRET", "")
    update = {"update_id": 987656}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            main.settings.WEBHOOK_PATH,
            headers={"X-Forwarded-For": "91.108.5.111"},
            json=update,
        )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_telegram_webhook_ignores_duplicate_update(monkeypatch) -> None:
    class CountingDispatcher:
        def __init__(self) -> None:
            self.calls = 0

        async def feed_update(self, bot, update) -> None:
            self.calls += 1

    dispatcher = CountingDispatcher()
    monkeypatch.setattr(main, "dp", dispatcher)
    monkeypatch.setattr(main, "bot", object())
    monkeypatch.setattr(main, "redis_client", None)
    main._recent_telegram_updates.clear()

    update = {
        "update_id": 987654,
        "message": {
            "message_id": 10,
            "date": 1779638390,
            "chat": {"id": 123, "type": "private", "first_name": "Test"},
            "from": {"id": 123, "is_bot": False, "first_name": "Test"},
            "text": "/start",
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            main.settings.WEBHOOK_PATH,
            headers={"X-Telegram-Bot-Api-Secret-Token": main.settings.WEBHOOK_SECRET},
            json=update,
        )
        second = await client.post(
            main.settings.WEBHOOK_PATH,
            headers={"X-Telegram-Bot-Api-Secret-Token": main.settings.WEBHOOK_SECRET},
            json=update,
        )

    await asyncio.sleep(0)
    assert first.status_code == 200
    assert second.status_code == 200
    assert dispatcher.calls == 1
