# bot/states/__init__.py
from aiogram.fsm.state import State, StatesGroup


class ImageGenFSM(StatesGroup):
    model_select = State()
    mode_select = State()          # text / image (for Wan i2i)
    aspect_ratio_select = State()  # for Wan 2.7 Pro
    count_select = State()         # for Wan 2.7 Pro
    image_upload = State()         # optional img2img
    prompt_input = State()
    generating = State()


class VideoGenFSM(StatesGroup):
    model_select = State()
    mode_select = State()           # text / image
    image_upload = State()          # optional i2v
    params_select = State()         # duration + aspect_ratio + resolution
    motion_select = State()         # only for Kling 2.6 Motion
    prompt_input = State()
    generating = State()


class MidjourneyFSM(StatesGroup):
    # Imagine flow
    bot_type_select = State()
    speed_select = State()
    prompt_input = State()
    image_upload = State()
    generating = State()

    viewing_result = State()
    action_polling = State()
    waiting_modal_input = State()

    # Blend flow
    blend_collecting = State()
    blend_generating = State()

    # Describe flow
    describe_upload = State()
    describe_polling = State()

    # MJ Video flow
    video_upload = State()
    video_speed_select = State()
    video_prompt = State()
    video_generating = State()
