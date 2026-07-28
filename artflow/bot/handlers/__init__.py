"""Telegram handler package bootstrap."""

# Importing these modules installs high-priority repeat handlers into the
# existing image/feed/marketplace routers before main.py includes them in the
# dispatcher.
from bot.handlers import repeat_references as _repeat_references  # noqa: F401
from bot.handlers import repeat_reference_marketplace as _repeat_reference_marketplace  # noqa: F401
