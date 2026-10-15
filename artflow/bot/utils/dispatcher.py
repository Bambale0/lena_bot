from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import SimpleEventIsolation

from bot.middlewares.navigation import NavigationMiddleware


def create_dispatcher(storage: BaseStorage) -> Dispatcher:
    """Serialize updates sharing an FSM key so media albums cannot lose state."""
    isolation_factory = getattr(storage, "create_isolation", None)
    if callable(isolation_factory):
        try:
            # Cover max Telegram video download (300s), provider wait (180s),
            # and cleanup so a retry cannot start a second paid analysis.
            events_isolation = isolation_factory(lock_kwargs={"timeout": 600})
        except TypeError:
            events_isolation = isolation_factory()
    else:
        events_isolation = SimpleEventIsolation()
    dispatcher = Dispatcher(storage=storage, events_isolation=events_isolation)
    dispatcher.callback_query.middleware(NavigationMiddleware())
    dispatcher.message.middleware(NavigationMiddleware())
    return dispatcher
