from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core import admin_alerts


class _FakeSession:
    def __init__(self) -> None:
        self.close = AsyncMock()


class _FakeBot:
    def __init__(self, side_effects: list[object] | None = None) -> None:
        self.session = _FakeSession()
        if side_effects is None:
            self.send_message = AsyncMock(return_value=True)
        else:
            self.send_message = AsyncMock(side_effect=side_effects)


@pytest.mark.asyncio
async def test_send_admin_alert_once_sets_cooldown_only_after_success(monkeypatch) -> None:
    admin_alerts._ALERT_STATE.clear()
    first_bot = _FakeBot(side_effects=[RuntimeError("boom")])
    second_bot = _FakeBot()
    bots = [first_bot, second_bot]

    monkeypatch.setattr(admin_alerts, "Bot", lambda *args, **kwargs: bots.pop(0))
    monkeypatch.setattr(admin_alerts.settings, "ADMIN_IDS", [1])

    first = await admin_alerts.send_admin_alert_once(alert_key="credits:test", title="t", message="m", cooldown_seconds=3600)
    second = await admin_alerts.send_admin_alert_once(alert_key="credits:test", title="t", message="m", cooldown_seconds=3600)

    assert first is False
    assert second is True
    assert first_bot.send_message.await_count == 1
    assert second_bot.send_message.await_count == 1


@pytest.mark.asyncio
async def test_send_admin_alert_once_respects_cooldown_after_success(monkeypatch) -> None:
    admin_alerts._ALERT_STATE.clear()
    bot = _FakeBot()

    monkeypatch.setattr(admin_alerts, "Bot", lambda *args, **kwargs: bot)
    monkeypatch.setattr(admin_alerts.settings, "ADMIN_IDS", [1])

    first = await admin_alerts.send_admin_alert_once(alert_key="credits:ok", title="t", message="m", cooldown_seconds=3600)
    second = await admin_alerts.send_admin_alert_once(alert_key="credits:ok", title="t", message="m", cooldown_seconds=3600)

    assert first is True
    assert second is False
    assert bot.send_message.await_count == 1
