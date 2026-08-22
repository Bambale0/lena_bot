from __future__ import annotations

from api import seedance25_adapter as s25
from api import seedance25_product_surface as s25_surface
from bot.keyboards import models as keyboard_models


def test_feed_video_repeat_i2v_keyboard_renders_seedance25_button() -> None:
    """Mirror feed.py's exact ``video_models_kb(model_costs, 'i2v')`` path."""
    s25.install_seedance25_provider_support()
    s25_surface.install_seedance25_product_surface()

    markup = keyboard_models.video_models_kb([s25._model_cost()], "i2v")
    buttons = [button for row in markup.inline_keyboard for button in row]

    matching = [
        button
        for button in buttons
        if button.callback_data == f"vid_model:{s25.MODEL_KEY}"
    ]
    assert len(matching) == 1
    assert "Seedance 2.5" in matching[0].text
