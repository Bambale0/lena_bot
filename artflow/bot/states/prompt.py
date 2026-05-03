# bot/states/prompt.py
from aiogram.fsm.state import State, StatesGroup


class PromptUploadFSM(StatesGroup):
    title = State()
    description = State()
    category = State()
    prompt_text = State()
    confirm = State()


class PromptModerateFSM(StatesGroup):
    reject_reason = State()
