from dataclasses import dataclass
from types import SimpleNamespace

from api.image_service import ImageModel
from api.video_service import VideoModel
from bot.keyboards import models as model_keyboards
from bot.ui.model_labels import (
    all_known_model_keys,
    apply_model_labels,
    canonical_model_key,
    install_miniapp_model_labels,
    is_internal_variant,
    model_display_name,
    public_model_items,
)


@dataclass
class FakeCost:
    model_key: str
    display_name: str


def test_seedream_5_pro_is_one_hot_public_model():
    text = model_display_name("seedream/5-pro-text-to-image")
    edit = model_display_name("seedream/5-pro-image-to-image")
    assert text == "🔥 HOT · Seedream 5 Pro"
    assert edit == text
    assert canonical_model_key("seedream/5-pro-image-to-image") == "seedream/5-pro-text-to-image"


def test_grok_video_1_and_15_are_separate_public_models():
    legacy_text = model_display_name("grok-imagine/text-to-video")
    legacy_image = model_display_name("grok-imagine/image-to-video")
    new_model = model_display_name("grok-imagine-video-1-5-preview")

    assert legacy_text == "⚡ Grok Imagine Video"
    assert legacy_image == legacy_text
    assert new_model == "🆕 NEW · Grok Imagine Video 1.5"
    assert new_model != legacy_text
    assert canonical_model_key("grok-imagine/image-to-video") == "grok-imagine/text-to-video"
    assert canonical_model_key("grok-imagine-video-1-5-preview") == "grok-imagine-video-1-5-preview"


def test_all_text_and_reference_route_pairs_share_public_name():
    pairs = [
        ("seedream/4.5-text-to-image", "seedream/4.5-edit"),
        ("grok-imagine/text-to-image", "grok-imagine/image-to-image"),
        ("qwen/text-to-image", "qwen/image-to-image"),
        ("qwen2/text-to-image", "qwen2/image-edit"),
        ("gpt-image-2-text-to-image", "gpt-image-2-image-to-image"),
        ("kling-2.6/text-to-video", "kling-2.6/image-to-video"),
        ("kling/v3-turbo-text-to-video", "kling/v3-turbo-image-to-video"),
        ("wan/2-7-text-to-video", "wan/2-7-image-to-video"),
        ("grok-imagine/text-to-video", "grok-imagine/image-to-video"),
        ("happyhorse/text-to-video", "happyhorse/image-to-video"),
    ]
    for canonical, variant in pairs:
        assert model_display_name(canonical) == model_display_name(variant)
        assert canonical_model_key(variant) == canonical
        assert is_internal_variant(variant)
        assert not is_internal_variant(canonical)


def test_every_runtime_image_and_video_model_has_explicit_public_label():
    known = all_known_model_keys()
    assert {item.value for item in ImageModel} - known == set()
    assert {item.value for item in VideoModel} - known == set()


def test_every_runtime_model_label_starts_with_emoji_or_badge():
    for key in all_known_model_keys():
        label = model_display_name(key)
        assert label
        assert label[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def test_motion_and_quality_variants_remain_distinct_products():
    assert model_display_name("kling-2.6/motion-control") != model_display_name("kling-2.6/text-to-video")
    assert model_display_name("kling-3.0/motion-control") != model_display_name("kling-3.0/video")
    assert model_display_name("wan/2-7-image-pro") != model_display_name("wan/2-7-image")
    assert model_display_name("veo3_fast") != model_display_name("veo3")


def test_public_picker_collapses_internal_routes_but_keeps_grok_generations_separate():
    rows = [
        FakeCost("seedream/5-pro-text-to-image", "old text"),
        FakeCost("seedream/5-pro-image-to-image", "old edit"),
        FakeCost("grok-imagine/text-to-video", "old video"),
        FakeCost("grok-imagine/image-to-video", "old animate"),
        FakeCost("grok-imagine-video-1-5-preview", "new video"),
    ]
    public = public_model_items(rows)
    assert [item.model_key for item in public] == [
        "seedream/5-pro-text-to-image",
        "grok-imagine/text-to-video",
        "grok-imagine-video-1-5-preview",
    ]
    assert [item.display_name for item in public] == [
        "🔥 HOT · Seedream 5 Pro",
        "⚡ Grok Imagine Video",
        "🆕 NEW · Grok Imagine Video 1.5",
    ]


def test_label_only_normalization_preserves_internal_routes():
    rows = [
        FakeCost("kling-2.6/text-to-video", "Kling text"),
        FakeCost("kling-2.6/image-to-video", "Kling animate"),
    ]
    normalized = apply_model_labels(rows)
    assert len(normalized) == 2
    assert normalized[0].display_name == normalized[1].display_name == "🎬 Kling 2.6"


def test_miniapp_uses_shared_catalog_instead_of_legacy_names():
    module = SimpleNamespace(
        _FRIENDLY_MODEL_NAMES={"seedream/5-pro-image-to-image": "Seedream Edit"},
        _friendly_model_name=lambda key, display=None: display or key,
    )
    install_miniapp_model_labels(module)
    assert module._friendly_model_name("seedream/5-pro-image-to-image") == "🔥 HOT · Seedream 5 Pro"
    assert module._friendly_model_name("grok-imagine/image-to-video") == "⚡ Grok Imagine Video"
    assert module._friendly_model_name("grok-imagine-video-1-5-preview") == "🆕 NEW · Grok Imagine Video 1.5"
    assert "Edit" not in module._friendly_model_name("gpt-image-2-image-to-image")
    assert "Animate" not in module._friendly_model_name("happyhorse/image-to-video")


def test_actual_legacy_button_renderer_keeps_old_grok_name():
    cost = SimpleNamespace(
        model_key="grok-imagine/image-to-video",
        display_name="⚡ Grok Animate",
        credits=0.6,
    )
    button = model_keyboards._model_button(cost, "vid_model", [cost])
    assert button.text == "⚡ Grok Imagine Video · 0.6 💋/сек"
    assert button.callback_data == "vid_model:grok-imagine/image-to-video"
    assert "Animate" not in button.text
