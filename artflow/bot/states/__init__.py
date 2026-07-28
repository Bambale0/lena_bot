# bot/states/__init__.py
from aiogram.fsm.state import State, StatesGroup


class ImageGenFSM(StatesGroup):
    model_select = State()
    mode_select = State()
    image_upload = State()
    reference_upload = State()  # optional reference image
    aspect_ratio_select = State()
    count_select = State()
    prompt_input = State()
    review = State()
    generating = State()
    session_active = State()
    remix_prompt = State()
    session_reference_upload = State()
    photo_to_prompt = State()
    photo_to_prompt_ref = State()
    photo_to_prompt_model = State()


class VideoGenFSM(StatesGroup):
    model_select = State()
    mode_select = State()           # text / image / video
    image_upload = State()          # image references and motion assets
    video_upload = State()          # dedicated reference video upload
    params_select = State()         # duration + aspect_ratio + resolution
    motion_select = State()         # only for Kling motion
    omni_ids_input = State()        # Gemini Omni audio_ids / character_ids / seed
    omni_audio_input = State()      # Gemini Omni audio ID utility
    omni_character_image = State()  # Gemini Omni character utility, reference image
    omni_character_input = State()  # Gemini Omni character utility, metadata
    prompt_input = State()
    review = State()                # final task + price review before charging
    generating = State()


class MidjourneyFSM(StatesGroup):
    bot_type_select = State()
    speed_select = State()
    reference_upload = State()
    prompt_input = State()
    image_upload = State()
    generating = State()
    viewing_result = State()
    action_polling = State()
    waiting_modal_input = State()
    blend_collecting = State()
    blend_generating = State()
    describe_upload = State()
    describe_polling = State()
    video_upload = State()
    video_speed_select = State()
    video_prompt = State()
    video_generating = State()


class MusicFSM(StatesGroup):
    prompt_input = State()


class PromptUseFSM(StatesGroup):
    model_select = State()
    reference_upload = State()


class AssistantFSM(StatesGroup):
    waiting_message = State()


class AdminStates(StatesGroup):
    waiting_ai_request = State()
    confirming_ai_action = State()


class PromoFSM(StatesGroup):
    waiting_code = State()
