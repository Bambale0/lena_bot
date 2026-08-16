from types import SimpleNamespace

import api  # noqa: F401 - initialize provider adapters before repository imports

from bot.ui.main_menu import render_main_menu


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
    markup = render_main_menu(ctx).reply_markup

    assert "menu:admin" in _callbacks(markup)
    assert "👑 Админ-панель" in _labels(markup)
    assert "menu:test" in _callbacks(markup)
    assert "🧪 Тест" in _labels(markup)


def test_admin_button_is_hidden_from_regular_users():
    ctx = SimpleNamespace(balance=100, active_image_session=None, is_admin=False)
    markup = render_main_menu(ctx).reply_markup

    assert "menu:admin" not in _callbacks(markup)
    assert "menu:test" not in _callbacks(markup)
    assert "🧪 Тест" not in _labels(markup)
