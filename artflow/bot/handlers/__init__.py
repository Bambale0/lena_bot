"""Telegram handler package bootstrap."""

# Importing this module installs high-priority repeat handlers into the existing
# image/feed routers before main.py includes those routers in the dispatcher.
from bot.handlers import repeat_references as _repeat_references  # noqa: F401
