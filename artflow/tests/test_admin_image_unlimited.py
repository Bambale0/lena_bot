from __future__ import annotations

from types import SimpleNamespace

from db.models import GenerationType
from bot.keyboards.admin_unlimited import (
    eligible_image_models,
    image_unlimited_models_kb,
)


def _cost(model_id: int, key: str, name: str, gen_type: GenerationType):
    return SimpleNamespace(
        id=model_id,
        model_key=key,
        display_name=name,
        gen_type=gen_type,
        is_active=True,
    )


def test_eligible_image_models_excludes_video_and_pricing_variants() -> None:
    costs = [
        _cost(1, "nano-banana-2", "Nano Banana 2", GenerationType.image),
        _cost(2, "nano-banana-2__quality=4K", "Nano Banana 2 4K", GenerationType.image),
        _cost(3, "veo3", "Veo", GenerationType.video),
        _cost(4, "gpt-image-2-text-to-image", "GPT Image 2", GenerationType.image),
    ]

    result = eligible_image_models(costs)

    assert [item.id for item in result] == [4, 1]


def test_image_unlimited_keyboard_marks_enabled_models_and_uses_short_callbacks() -> None:
    costs = [
        _cost(11, "nano-banana-2", "Nano Banana 2", GenerationType.image),
        _cost(12, "seedream/5-pro-text-to-image", "Seedream 5 Pro", GenerationType.image),
    ]

    markup = image_unlimited_models_kb(costs, enabled_model_ids={12})
    buttons = [button for row in markup.inline_keyboard for button in row]
    by_callback = {button.callback_data: button.text for button in buttons if button.callback_data}

    assert by_callback["adm:iu:toggle:11"].startswith("▫️")
    assert by_callback["adm:iu:toggle:12"].startswith("✅")
    assert "adm:iu:clear" in by_callback
    assert "adm:iu:other" in by_callback
    assert all(len(callback) <= 64 for callback in by_callback)
