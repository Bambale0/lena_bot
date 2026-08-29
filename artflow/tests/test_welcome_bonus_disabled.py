from __future__ import annotations

from core.config import Settings


def test_welcome_bonus_stays_disabled_when_legacy_env_requests_credits(monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:welcome-bonus-test")
    monkeypatch.setenv("COMET_API_KEY", "welcome-bonus-test")
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("WELCOME_BONUS_CREDITS", "3")

    config = Settings(_env_file=None)

    assert config.WELCOME_BONUS_CREDITS == 0
