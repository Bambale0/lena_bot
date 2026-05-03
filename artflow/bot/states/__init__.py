# bot/states/image_gen.py
from aiogram.fsm.state import State, StatesGroup


class ImageGenFSM(StatesGroup):
    model_select = State()
    prompt_input = State()
    image_upload = State()   # optional img2img
    generating = State()


# bot/states/video_gen.py
class VideoGenFSM(StatesGroup):
    model_select = State()
    mode_select = State()     # text / image
    motion_select = State()   # only for Kling 2.6 Motion
    image_upload = State()    # optional
    prompt_input = State()
    generating = State()


# bot/states/midjourney.py
class MidjourneyFSM(StatesGroup):
    # Imagine flow
    bot_type_select = State()      # MID_JOURNEY / NIJI_JOURNEY
    speed_select = State()         # FAST / RELAX / TURBO
    prompt_input = State()
    image_upload = State()         # optional img2img
    generating = State()

    viewing_result = State()       # result shown + action buttons
    action_polling = State()       # button clicked, polling new task

    waiting_modal_input = State()  # Custom Zoom / Vary Region

    # Blend flow
    blend_collecting = State()     # collecting 2-5 images
    blend_generating = State()

    # Describe flow
    describe_upload = State()
    describe_polling = State()

    # MJ Video flow
    video_upload = State()         # upload first frame
    video_speed_select = State()   # low / high
    video_prompt = State()
    video_generating = State()
