from __future__ import annotations

from core.config import Settings


def _base_env(monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:welcome-bonus-test")
    monkeypatch.setenv("COMET_API_KEY", "welcome-bonus-test")
    monkeypatch.setenv("ENV", "test")


def test_welcome_bonus_defaults_to_three(monkeypatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.delenv("WELCOME_BONUS_CREDITS", raising=False)

    config = Settings(_env_file=None)

    assert config.WELCOME_BONUS_CREDITS == 3


def test_welcome_bonus_honors_explicit_setting(monkeypatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("WELCOME_BONUS_CREDITS", "3")

    config = Settings(_env_file=None)

    assert config.WELCOME_BONUS_CREDITS == 3
