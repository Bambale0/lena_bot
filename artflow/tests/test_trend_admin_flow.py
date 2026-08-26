from __future__ import annotations

from enum import Enum
from types import SimpleNamespace

from bot.services import trend_admin_flow


class _Kind(str, Enum):
    image = "image"
    video = "video"


def _cost(model_key: str, gen_type, *, active: bool = True):
    return SimpleNamespace(
        model_key=model_key,
        display_name=model_key,
        gen_type=gen_type,
        is_active=active,
    )


def test_generation_type_value_accepts_enum_and_plain_text() -> None:
    assert trend_admin_flow._generation_type_value(_cost("x", _Kind.image)) == "image"
    assert trend_admin_flow._generation_type_value(_cost("x", "video")) == "video"


def test_available_models_uses_plain_text_generation_type() -> None:
    image_key = next(iter(trend_admin_flow.IMAGE_CAPS))
    video_key = next(iter(trend_admin_flow.VIDEO_CAPS))
    costs = [
        _cost(image_key, "image"),
        _cost(video_key, "video"),
    ]

    assert [item.model_key for item in trend_admin_flow._available_models(costs, "image")] == [image_key]
    assert [item.model_key for item in trend_admin_flow._available_models(costs, "video")] == [video_key]


def test_available_models_falls_back_to_runtime_capabilities() -> None:
    image_key = next(iter(trend_admin_flow.IMAGE_CAPS))
    video_key = next(iter(trend_admin_flow.VIDEO_CAPS))
    costs = [
        _cost(image_key, None),
        _cost(video_key, None),
        _cost("unknown-model", None),
    ]

    assert [item.model_key for item in trend_admin_flow._available_models(costs, "image")] == [image_key]
    assert [item.model_key for item in trend_admin_flow._available_models(costs, "video")] == [video_key]


def test_available_models_never_returns_inactive_rows() -> None:
    image_key = next(iter(trend_admin_flow.IMAGE_CAPS))
    costs = [_cost(image_key, "image", active=False)]

    assert trend_admin_flow._available_models(costs, "image") == []
