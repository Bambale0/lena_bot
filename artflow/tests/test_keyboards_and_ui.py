from __future__ import annotations

from types import SimpleNamespace

from bot.keyboards.main_menu import back_to_menu_kb, main_menu_kb
from bot.keyboards.payment import topup_kb
from bot.ui.main_menu import render_main_menu


def flatten_buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_main_menu_keyboard_keeps_core_buttons() -> None:
    buttons = flatten_buttons(main_menu_kb(balance=100, has_active_image_session=True, is_admin=True))
    texts = [button.text for button in buttons]
    assert "🎨 Изображение" in texts
    assert "📚 Библиотека промптов" in texts
    assert "👑 Админ" in texts


def test_back_to_menu_keyboard_has_main_callback() -> None:
    buttons = flatten_buttons(back_to_menu_kb())
    assert buttons[0].callback_data == "menu:main"


def test_render_main_menu_includes_webapp_button() -> None:
    context = SimpleNamespace(balance=1003, active_image_session=None, is_admin=False)
    render = render_main_menu(context)
    buttons = flatten_buttons(render.reply_markup)
    web_buttons = [button for button in buttons if button.text == "📱 Открыть приложение"]
    assert web_buttons and web_buttons[0].web_app.url.endswith("/app")


def test_render_main_menu_active_session_text() -> None:
    session = SimpleNamespace(model="nano-banana-pro", quality="2K", aspect_ratio="9:16", count=3)
    context = SimpleNamespace(balance=1003, active_image_session=session, is_admin=False)
    render = render_main_menu(context)
    assert "Активная серия найдена" in render.text
def test_topup_keyboard_keeps_decimal_price() -> None:
    plans = [SimpleNamespace(label="10 сек · Pro", price_rub=199.5, key="p1")]
    buttons = flatten_buttons(topup_kb(plans))
    assert buttons[0].text == "💳 10 сек · Pro — 199.5₽"
