from __future__ import annotations

from payments import cryptobot


def test_paid_button_url_uses_bot_username(monkeypatch) -> None:
    monkeypatch.setattr(cryptobot.settings, "BOT_USERNAME", "@ApixRealBot")

    assert cryptobot._paid_button_url() == "https://t.me/ApixRealBot"
