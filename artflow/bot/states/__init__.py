# bot/states/image_gen.py
from aiogram.fsm.state import State, StatesGroup


class ImageGenFSM(StatesGroup):
    model_select = State()
    prompt_input = State()
    image_upload = State()   # optional img2img
    generating = State()


# bot/states/video_gen.py
from aiogram.fsm.state import State, StatesGroup


class VideoGenFSM(StatesGroup):
    model_select = State()
    mode_select = State()     # text / image
    motion_select = State()   # only for Kling 2.6 Motion
    image_upload = State()    # optional
    prompt_input = State()
    generating = State()
