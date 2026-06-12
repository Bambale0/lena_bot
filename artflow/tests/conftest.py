from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["BOT_TOKEN"] = "123456:test-token"
os.environ["BOT_USERNAME"] = "TestBot"
os.environ["WEBHOOK_URL"] = "https://example.test"
os.environ["WEBHOOK_SECRET"] = "test-secret"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost:5432/test"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["COMET_API_KEY"] = "test-comet-key"
os.environ["ENV"] = "test"
os.environ["APIX_WEB_DEV_AUTH"] = "false"
os.environ["TELEGRAM_STARS_ENABLED"] = "false"
os.environ["KIE_WEBHOOK_SECRET"] = ""


@pytest.fixture
def bot() -> AsyncMock:
    bot = AsyncMock()
    bot.id = 987654321
    bot.username = "TestBot"
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()
    return bot
