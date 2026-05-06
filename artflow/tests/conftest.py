from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("BOT_USERNAME", "TestBot")
os.environ.setdefault("WEBHOOK_URL", "https://example.test")
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("COMET_API_KEY", "test-comet-key")


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
