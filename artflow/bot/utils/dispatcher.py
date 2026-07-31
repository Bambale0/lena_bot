from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import SimpleEventIsolation


def create_dispatcher(storage: BaseStorage) -> Dispatcher:
    """Serialize updates sharing an FSM key so media albums cannot lose state."""
    isolation_factory = getattr(storage, "create_isolation", None)
    events_isolation = isolation_factory() if callable(isolation_factory) else SimpleEventIsolation()
    return Dispatcher(storage=storage, events_isolation=events_isolation)
