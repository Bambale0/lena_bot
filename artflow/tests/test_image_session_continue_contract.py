from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_MENU = ROOT / "bot" / "ui" / "main_menu.py"
MODEL_FIRST_HANDLER = ROOT / "bot" / "handlers" / "image_models_first.py"


def test_main_menu_continue_does_not_reenter_new_image_model_picker() -> None:
    source = MAIN_MENU.read_text(encoding="utf-8")

    assert 'callback_data="img_session:continue"' in source
    assert 'text="🔥 " + ("Продолжить" if lang == "ru" else "Continue"), callback_data="menu:image"' not in source


def test_active_session_continue_restores_saved_session_state() -> None:
    source = MODEL_FIRST_HANDLER.read_text(encoding="utf-8")

    assert '@router.callback_query(F.data == "img_session:continue")' in source
    assert "await repo.get_active_image_session(session, db_user.id)" in source
    assert "from bot.handlers.image_gen import _show_active_image_session_callback" in source
    assert "await _show_active_image_session_callback(call, state, session, db_user, image_session)" in source
