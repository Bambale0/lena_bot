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
    assert 'back_callback="menu:main"' in source
    entry_handler = source.split("async def open_image_models_first(", 1)[1].split(
        "\n\n@router.", 1
    )[0]
    assert "get_active_image_session" not in entry_handler


def test_change_model_picker_returns_to_task_without_looping() -> None:
    source = MODEL_FIRST_HANDLER.read_text(encoding="utf-8")

    assert 'F.data == "img_menu:advanced"' in source
    assert 'back_callback = "img_v2:back"' in source
    assert 'back_text = "← К задаче"' in source



def test_reachable_first_image_menu_exposes_nana_banano_quick_flow() -> None:
    from bot.handlers.image_models_first import _model_list_kb
    menu = _model_list_kb([], back_text="🏠 Главное меню", back_callback="menu:main")
    buttons = [button for row in menu.inline_keyboard for button in row]
    assert any(button.text.startswith("🍌 nana banano") and button.callback_data == "img_scn:fast" for button in buttons)


def test_legacy_image_composer_screen_exposes_nana_quick_entry() -> None:
    from bot.ui.image_menu import render_image_scenarios
    buttons = [button for row in render_image_scenarios().reply_markup.inline_keyboard for button in row]
    assert any(button.callback_data == "img_scn:fast" for button in buttons)



def test_model_first_nana_button_routes_into_existing_quick_composer() -> None:
    # The live model-first menu owns menu:image. Its quick button must reach
    # the existing no-state-filter img_scn:fast handler, not a dead menu.
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from bot.handlers import image_gen

    async def run() -> None:
        call = SimpleNamespace(data="img_scn:fast", message=SimpleNamespace(), answer=AsyncMock())
        state = AsyncMock()
        db_session = object()
        db_user = SimpleNamespace(id=42, credits=10)
        with patch.object(image_gen, "_show_nana_banano_flow", AsyncMock(return_value=True)) as open_quick:
            with patch.object(image_gen, "safe_answer_callback", AsyncMock()) as answer:
                await image_gen.cb_image_scenario(call, db_session, state, db_user)
        assert open_quick.await_args.kwargs == {
            "call": call, "session": db_session, "state": state, "db_user": db_user,
            "model_key": image_gen.IMAGE_SCENARIOS["fast"]["model"],
            "preserve_refs": False,
        }
        answer.assert_awaited_once_with(call)

    asyncio.run(run())
