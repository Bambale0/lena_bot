from types import SimpleNamespace

from bot.keyboards.main_menu import main_menu_kb
from bot.ui.main_menu import render_main_menu


def callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def test_legacy_and_ui_main_menu_have_same_callbacks_without_session():
    ctx = SimpleNamespace(
        balance=100,
        active_image_session=None,
        is_admin=False,
    )

    ui = callbacks(render_main_menu(ctx).reply_markup)
    legacy = callbacks(main_menu_kb(balance=100, has_active_image_session=False, is_admin=False))

    assert set(ui) == set(legacy)


def test_main_menu_has_no_unstable_top_day_or_midjourney_entrypoints():
    ctx = SimpleNamespace(
        balance=100,
        active_image_session=None,
        is_admin=False,
    )

    cb = callbacks(render_main_menu(ctx).reply_markup)

    assert "menu:top_day" not in cb
    assert "menu:mj" in cb


def test_main_menu_core_callbacks():
    ctx = SimpleNamespace(
        balance=100,
        active_image_session=None,
        is_admin=False,
    )

    cb = callbacks(render_main_menu(ctx).reply_markup)

    assert cb == [
        "menu:balance",
        "menu:image",
        "menu:video",
        "menu:music",
        "menu:mj",
        "menu:assistant",
        "menu:feed",
        "menu:prompts",
        "menu:history",
        "menu:referral",
        "menu:help",
        "menu:topup",
        "menu:settings",
    ]
