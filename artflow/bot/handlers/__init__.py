"""Handler package bootstrap.

UX v2 routers are registered before the legacy technical flow. Provider-backed
capability patches are installed before keyboards and handlers render models.
"""
from aiogram import Router
from aiogram.types import InlineKeyboardButton

from bot.keyboards import models as _model_keyboards
from bot.services.grok_versions import install_grok_versions
from bot.services.image_family_routing import install_image_family_routing
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

# Image UX v2: direct task-first flow first, legacy expert flow second.
from . import image_gen as _legacy_image_gen
from . import repeat_reference_marketplace as _repeat_reference_marketplace  # noqa: F401
from . import repeat_references as _repeat_references  # noqa: F401
from . import image_wizard_v2 as _image_wizard_v2

_image_router = Router(name="image_v2")
_image_router.include_router(_image_wizard_v2.router)
_image_router.include_router(_legacy_image_gen.router)
_legacy_image_gen.router = _image_router

# Video UX v2: scenario wizard first, legacy technical flow second.
from . import video_gen as _legacy_video_gen
from . import video_references as _video_references
from . import video_wizard as _video_wizard

_video_router = Router(name="video_v2")
_video_router.include_router(_video_references.router)
_video_router.include_router(_video_wizard.router)
_video_router.include_router(_legacy_video_gen.router)
_legacy_video_gen.router = _video_router
