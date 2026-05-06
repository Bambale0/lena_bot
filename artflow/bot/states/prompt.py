# bot/states/prompt.py
from aiogram.fsm.state import State, StatesGroup


class PromptUploadFSM(StatesGroup):
    upload_image = State()
    prompt_text = State()
    confirm = State()


class PromptModerateFSM(StatesGroup):
    reject_reason = State()
