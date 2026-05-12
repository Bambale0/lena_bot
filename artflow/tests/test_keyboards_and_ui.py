from __future__ import annotations

from types import SimpleNamespace

from bot.handlers.start import _help_text
from bot.keyboards.main_menu import back_to_menu_kb, main_menu_kb
from bot.keyboards.models import video_params_kb
from bot.keyboards.payment import topup_kb
from bot.ui.main_menu import render_main_menu


def flatten_buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_main_menu_keyboard_keeps_core_buttons() -> None:
    buttons = flatten_buttons(main_menu_kb(balance=100, has_active_image_session=True, is_admin=True))
    texts = [button.text for button in buttons]
    assert "🎨 Изображение" in texts
    assert "📚 Библиотека" in texts
    assert "👑 Админ" in texts


def test_back_to_menu_keyboard_has_main_callback() -> None:
    buttons = flatten_buttons(back_to_menu_kb())
    assert buttons[0].callback_data == "menu:main"


def test_render_main_menu_active_session_text() -> None:
    session = SimpleNamespace(model="nano-banana-pro", quality="2K", aspect_ratio="9:16", count=3)
    context = SimpleNamespace(balance=1003, active_image_session=session, is_admin=False)
    render = render_main_menu(context)
    assert "Текущая серия изображений" in render.text


def test_render_main_menu_force_main_text_even_with_active_session() -> None:
    session = SimpleNamespace(model="nano-banana-pro", quality="2K", aspect_ratio="9:16", count=3)
    context = SimpleNamespace(balance=1003, active_image_session=session, is_admin=False)
    render = render_main_menu(context, force_main_text=True)
    assert "Твоя AI-студия" in render.text
    assert "Выбирай, что запустить:" in render.text
    assert "Текущая серия изображений" not in render.text


def test_video_params_kb_hides_grok_i2v_ratio_for_single_ref() -> None:
    buttons = flatten_buttons(
        video_params_kb(
            "grok-imagine/image-to-video",
            6,
            None,
            "480p",
            "normal",
            selected_mode="image",
            ref_count=1,
        )
    )
    assert all(button.callback_data != "vpar_ratio:16:9" for button in buttons)


def test_help_text_contains_support_contact() -> None:
    text = _help_text("ru")
    assert "@LeLu88" in text


def test_help_text_explains_settings_plainly() -> None:
    text = _help_text("ru")
    assert "короткие и понятные промпты" in text
    assert "бот сам покажет их по ходу выбора" in text


def test_topup_keyboard_keeps_decimal_price() -> None:
    plans = [SimpleNamespace(label="10 сек · Pro", credits=10, price_rub=199.5, key="p1")]
    buttons = flatten_buttons(topup_kb(plans))
    assert buttons[0].text == "💳 10 сек · Pro — 10 💋 · 199.5₽"


def test_topup_keyboard_hides_stars_by_default() -> None:
    plans = [SimpleNamespace(label="15 💋", credits=15, price_rub=150.0, key="credits_15")]
    buttons = flatten_buttons(topup_kb(plans))
    assert all(button.callback_data != "topup:stars" for button in buttons)
