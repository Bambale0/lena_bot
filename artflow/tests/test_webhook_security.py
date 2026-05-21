from __future__ import annotations

import pytest
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
