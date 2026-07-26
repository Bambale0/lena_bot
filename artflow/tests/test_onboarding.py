from types import SimpleNamespace

from bot.handlers.start import _help_text, _onboarding_text, onboarding_kb
from bot.ui.navigation_v2 import render_more_hub


def callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def test_onboarding_explains_flow_and_balance():
    user = SimpleNamespace(full_name="Игорь", username=None, credits=25)
    text = _onboarding_text(user, "ru")

    assert "Привет, Игорь" in text
    assert "25 кредитов" in text
    assert "Стоимость всегда показывается до запуска" in text


def test_onboarding_routes_to_first_result_and_mini_app():
    markup = onboarding_kb("ru")

    assert callbacks(markup) == [
        "menu:image",
        "menu:video",
        "menu:music",
        "menu:assistant",
        "onboarding:skip",
    ]
    app_button = markup.inline_keyboard[2][0]
    assert app_button.web_app is not None
    assert app_button.web_app.url.endswith("/app")


def test_help_and_more_screen_do_not_expose_developer_contact():
    assert "chillcreative" not in _help_text("ru").lower()
    assert "разработчик" not in _help_text("ru").lower()

    screen = render_more_hub("ru")
    assert "chillcreative" not in screen.text.lower()
    assert "разработчик" not in screen.text.lower()
    assert all(
        "chillcreative" not in (button.text or "").lower()
        for row in screen.reply_markup.inline_keyboard
        for button in row
    )
