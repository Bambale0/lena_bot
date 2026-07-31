from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation

from bot.utils.dispatcher import create_dispatcher


def test_dispatcher_serializes_updates_for_same_fsm_key() -> None:
    dispatcher = create_dispatcher(MemoryStorage())

    assert isinstance(dispatcher.fsm.events_isolation, SimpleEventIsolation)
