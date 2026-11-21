from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import miniapp_routes, neironych_nano2, neironych_nano_pro_runtime
from bot.handlers import image_gen
from bot.keyboards.models import IMAGE_CAPS


def _buttons(markup):
    return {button.callback_data for row in markup.inline_keyboard for button in row}


@pytest.mark.parametrize("provider", ["neironych", "nexus"])
async def test_miniapp_catalog_matches_primary_provider(monkeypatch, provider):
    models = ["nano-banana-2", "nano-banana-pro", "nano-banana-pro-vip", "nano-banana-2.1"]
    mock_costs = [
        SimpleNamespace(model_key=key, display_name=key, credits=1.0)
        for key in models
    ]
    monkeypatch.setattr(miniapp_routes.repo, "get_all_model_costs", AsyncMock(return_value=mock_costs))
    monkeypatch.setattr(miniapp_routes, "_resolve_image_quality_prices", AsyncMock(return_value={}))
    monkeypatch.setattr(miniapp_routes, "get_nano2_route", AsyncMock(return_value=SimpleNamespace(primary_provider=provider)))
    monkeypatch.setattr(miniapp_routes, "get_nano_pro_route", AsyncMock(return_value=SimpleNamespace(primary_provider=provider)))

    result = await miniapp_routes.list_image_models(session=object(), user=object())
    caps = {model.key: model.aspect_ratios for model in result}
    if provider == "neironych":
        assert set(caps["nano-banana-2"]) == neironych_nano2.RATIOS
        assert set(caps["nano-banana-pro"]) == neironych_nano_pro_runtime.RATIOS
        assert set(caps["nano-banana-pro-vip"]) == neironych_nano_pro_runtime.RATIOS
    else:
        for key in models:
            assert caps[key] == IMAGE_CAPS[key]["aspect_ratios"]

    assert caps["nano-banana-2.1"] == IMAGE_CAPS["nano-banana-2.1"]["aspect_ratios"]


@pytest.mark.parametrize("provider", ["neironych", "nexus"])
async def test_telegram_ratio_picker_matches_primary_provider(monkeypatch, provider):
    monkeypatch.setattr(image_gen, "get_nano2_route", AsyncMock(return_value=SimpleNamespace(primary_provider=provider)))
    monkeypatch.setattr(image_gen, "get_nano_pro_route", AsyncMock(return_value=SimpleNamespace(primary_provider=provider)))

    for model, supported in [
        ("nano-banana-2", neironych_nano2.RATIOS),
        ("nano-banana-pro", neironych_nano_pro_runtime.RATIOS),
        ("nano-banana-pro-vip", neironych_nano_pro_runtime.RATIOS),
    ]:
        markup = await image_gen._image_aspect_ratio_keyboard(model, session=object())
        actual = {button.removeprefix("img_ratio:") for button in _buttons(markup) if button.startswith("img_ratio:")}
        if provider == "neironych":
            assert actual == supported
        else:
            assert actual == set(IMAGE_CAPS[model]["aspect_ratios"])
