"""Handler package bootstrap.

UX v2 routers are registered before the legacy technical flow. Provider-backed
capability patches are installed before keyboards and handlers render models.
"""
from aiogram import Router
from aiogram.types import InlineKeyboardButton

from api.minimax_h3_adapter import install_minimax_h3_wizard_support
from api.repeat_runtime import install_image_launch_snapshot
from bot.keyboards import models as _model_keyboards
from bot.services.grok_versions import install_grok_versions
from bot.services.image_family_routing import install_image_family_routing
from bot.services.image_reference_prompt_flow import install_image_reference_prompt_flow
from bot.services.minimax_h3_ui import install_minimax_h3_handler_presentation
from bot.services.trend_admin_flow import build_trend_admin_router
from bot.services.veo_ui import install_veo_handler_presentation
from bot.services.video_reference_support import install_video_reference_support
from bot.ui.model_labels import model_display_name, public_model_items

install_image_family_routing()
install_video_reference_support()
install_grok_versions()


def _public_model_button(mc, prefix: str, model_costs: list) -> InlineKeyboardButton:
    """Render a provider route as one user-facing model family."""
    price_txt = _model_keyboards.model_cost_display_text(mc, model_costs=model_costs)
    public_name = model_display_name(mc.model_key, getattr(mc, "display_name", None))
    return InlineKeyboardButton(
        text=f"{public_name} · {price_txt}",
        callback_data=f"{prefix}:{mc.model_key}",
    )


_original_video_models_kb = _model_keyboards.video_models_kb


def _public_video_models_kb(model_costs: list, group_key: str | None = None):
    visible_costs = model_costs if group_key else public_model_items(model_costs)
    return _original_video_models_kb(visible_costs, group_key=group_key)


_model_keyboards._model_button = _public_model_button
_model_keyboards.video_models_kb = _public_video_models_kb

for _key, _description in list(_model_keyboards.VIDEO_MODEL_DESC.items()):
    _suffix = _description.split(" · ", 1)[1] if " · " in _description else ""
    _label = model_display_name(str(_key), _description)
    _model_keyboards.VIDEO_MODEL_DESC[_key] = f"{_label} · {_suffix}" if _suffix else _label

for _key, _description in list(_model_keyboards.IMAGE_MODEL_DESC.items()):
    _suffix = _description.split(" · ", 1)[1] if " · " in _description else ""
    _label = model_display_name(str(_key), _description)
    _model_keyboards.IMAGE_MODEL_DESC[_key] = f"{_label} · {_suffix}" if _suffix else _label

from . import image_gen as _legacy_image_gen
from . import image_models_first as _image_models_first
from . import image_wizard_v2 as _image_wizard_v2
from . import photo_prompt as _photo_prompt
from . import repeat_callback_guard as _repeat_callback_guard
from . import repeat_reference_marketplace as _repeat_reference_marketplace  # noqa: F401
from . import repeat_references as _repeat_references  # noqa: F401
from . import repeat_safe as _repeat_safe

install_image_launch_snapshot(_legacy_image_gen)
install_image_reference_prompt_flow(_legacy_image_gen)
_repeat_callback_guard.install_repeat_confirmation_guard(_repeat_safe)
_photo_prompt.install_photo_prompt_keyboard_hooks(_legacy_image_gen)

_image_router = Router(name="image_v2")
_image_router.include_router(_repeat_callback_guard.router)
_image_router.include_router(_repeat_safe.router)
_image_router.include_router(_image_models_first.router)
_image_router.include_router(_image_wizard_v2.router)
_image_router.include_router(_photo_prompt.router)
_image_router.include_router(_legacy_image_gen.router)
_legacy_image_gen.router = _image_router

# Provider-specific automatic collectors must run before the generic mode picker.
from . import gemini_omni_recovery as _gemini_omni_recovery
from . import gemini_omni_references as _gemini_omni_references
from . import minimax_h3_references as _minimax_h3_references
from . import seedance25_references as _seedance25_references
from . import video_gen as _legacy_video_gen
from . import video_references as _video_references
from . import video_wizard as _video_wizard

install_minimax_h3_wizard_support(_video_wizard)
install_minimax_h3_handler_presentation(_legacy_video_gen)
install_veo_handler_presentation(_legacy_video_gen)

_video_router = Router(name="video_v2")
_video_router.include_router(_gemini_omni_references.router)
_video_router.include_router(_gemini_omni_recovery.router)
_video_router.include_router(_minimax_h3_references.router)
_video_router.include_router(_seedance25_references.router)
_video_router.include_router(_video_references.router)
_video_router.include_router(_video_wizard.router)
_video_router.include_router(_legacy_video_gen.router)
_legacy_video_gen.router = _video_router

# Trend admin category selection gets a guard before the legacy wizard. This
# keeps callback spinners short, accepts enum/string generation types, preserves
# the draft on configuration gaps, and falls back to runtime model capabilities.
from . import trends as _trends

_trends_router = Router(name="trends_v2")
_trends_router.include_router(build_trend_admin_router(_trends))
_trends_router.include_router(_trends.router)
_trends.router = _trends_router

# Admin-only Nexus provider evaluation rides under the existing admin router.
# The UI is admin-gated and the Nexus router itself is protected by IsAdmin.
from . import admin as _admin
from . import nexus_test as _nexus_test

_admin.router.include_router(_nexus_test.router)
