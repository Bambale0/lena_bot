"""Handler package bootstrap.

The UX v2 video wizard is registered before the legacy technical flow. This
keeps all old callbacks working while making task-first navigation the default.

Legacy model keyboards historically rendered ``ModelCost.display_name``
directly from the database. Apply the public catalog before importing handlers
so every old picker uses the same names as the v2 wizard and Mini App.
"""
from aiogram import Router
from aiogram.types import InlineKeyboardButton

from bot.keyboards import models as _model_keyboards
from bot.ui.model_labels import model_display_name, public_model_items


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
    # Scenario groups already contain only compatible provider routes. The full
    # expert catalog is collapsed by family so text/image endpoints are not
    # presented as separate products.
    visible_costs = model_costs if group_key else public_model_items(model_costs)
    return _original_video_models_kb(visible_costs, group_key=group_key)


_model_keyboards._model_button = _public_model_button
_model_keyboards.video_models_kb = _public_video_models_kb

# Replace stale prefixes in model info screens as well. Keep the useful
# capability description after the separator, but always use the canonical
# public model name before it.
for _key, _description in list(_model_keyboards.VIDEO_MODEL_DESC.items()):
    _suffix = _description.split(" · ", 1)[1] if " · " in _description else ""
    _label = model_display_name(str(_key), _description)
    _model_keyboards.VIDEO_MODEL_DESC[_key] = f"{_label} · {_suffix}" if _suffix else _label

for _key, _description in list(_model_keyboards.IMAGE_MODEL_DESC.items()):
    _suffix = _description.split(" · ", 1)[1] if " · " in _description else ""
    _label = model_display_name(str(_key), _description)
    _model_keyboards.IMAGE_MODEL_DESC[_key] = f"{_label} · {_suffix}" if _suffix else _label

from . import video_gen as _legacy_video_gen
from . import video_wizard as _video_wizard

_video_router = Router(name="video_v2")
_video_router.include_router(_video_wizard.router)
_video_router.include_router(_legacy_video_gen.router)
_legacy_video_gen.router = _video_router
