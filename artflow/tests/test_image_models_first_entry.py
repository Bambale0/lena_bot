from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDLERS_INIT = ROOT / "bot" / "handlers" / "__init__.py"
MODEL_FIRST_HANDLER = ROOT / "bot" / "handlers" / "image_models_first.py"


def test_model_first_router_precedes_existing_image_wizard() -> None:
    source = HANDLERS_INIT.read_text(encoding="utf-8")

    model_first = source.index("_image_router.include_router(_image_models_first.router)")
    wizard = source.index("_image_router.include_router(_image_wizard_v2.router)")
    legacy = source.index("_image_router.include_router(_legacy_image_gen.router)")

    assert model_first < wizard < legacy


def test_image_entry_opens_model_list_instead_of_resuming_active_session() -> None:
    source = MODEL_FIRST_HANDLER.read_text(encoding="utf-8")

    assert 'F.data == "menu:image"' in source
    assert "ImageGenFSM.model_select" in source
    assert "image_models_kb(model_costs)" in source
    assert "Шаг 1. Выбери модель" in source
    assert "get_active_image_session" not in source


def test_model_list_back_does_not_loop_into_the_same_screen() -> None:
    source = MODEL_FIRST_HANDLER.read_text(encoding="utf-8")

    assert "image_models_first_visible" in source
    assert 'screen="image_entry"' in source
