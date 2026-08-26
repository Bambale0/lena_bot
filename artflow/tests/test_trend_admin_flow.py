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


def test_category_callback_parser_accepts_existing_keyboard_payload() -> None:
    kind, category = trend_admin_flow._parse_category_callback("trends:category:featured")

    assert kind is None
    assert category == "featured"


def test_category_callback_parser_accepts_kind_aware_payload() -> None:
    assert trend_admin_flow._parse_category_callback("trends:category:video:featured") == (
        "video",
        "featured",
    )


def test_model_selector_keeps_provider_ids_out_of_callback_data() -> None:
    very_long_model_key = "provider/" + "x" * 120
    options, markup = trend_admin_flow._model_selector(
        [_cost(very_long_model_key, "video")]
    )

    assert options == {"0": very_long_model_key}
    button = markup.inline_keyboard[0][0]
    assert button.callback_data == "trends:model-option:0"
    assert len(button.callback_data.encode("utf-8")) <= 64


def test_trend_guard_avoids_fsm_state_filters_for_recovery() -> None:
    class _FakeState:
        category = object()
        model = object()
        scenario = object()
        preview = object()

    fake_trends = SimpleNamespace(
        TrendAdminFSM=_FakeState,
        TREND_CATEGORIES={"featured": {"title": "Тренды"}},
        _cancel_kb=lambda: None,
    )

    router = trend_admin_flow.build_trend_admin_router(fake_trends)
    handlers = router.callback_query.handlers

    assert len(handlers) == 2
    # Both category and compact-model callbacks match by callback data + admin only.
    assert all(len(handler.filters) == 2 for handler in handlers)
