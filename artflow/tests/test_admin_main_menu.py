import importlib
from types import SimpleNamespace


def _render_main_menu(context):
    # Provider adapters must be initialized before session_service imports db.repository.
    importlib.import_module("api")
    module = importlib.import_module("bot.ui.main_menu")
    return module.render_main_menu(context)


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_admin_button_is_visible_on_main_menu_for_admins():
    ctx = SimpleNamespace(balance=100, active_image_session=None, is_admin=True)
    markup = _render_main_menu(ctx).reply_markup

    assert "menu:admin" in _callbacks(markup)
    assert "👑 Админ-панель" in _labels(markup)
    assert "menu:test" in _callbacks(markup)
    assert "🧪 Тест" in _labels(markup)


def test_admin_button_is_hidden_from_regular_users():
    ctx = SimpleNamespace(balance=100, active_image_session=None, is_admin=False)
    markup = _render_main_menu(ctx).reply_markup

    assert "menu:admin" not in _callbacks(markup)
    assert "menu:test" not in _callbacks(markup)
    assert "🧪 Тест" not in _labels(markup)


def test_nexus_test_model_selector_includes_seedance25():
    importlib.import_module("api")
    module = importlib.import_module("bot.handlers.nexus_test")
    markup = module._model_selector_kb()

    assert "nxt:model:nano" in _callbacks(markup)
    assert "nxt:model:seedance25" in _callbacks(markup)
    assert "🎬 Seedance 2.5" in _labels(markup)
