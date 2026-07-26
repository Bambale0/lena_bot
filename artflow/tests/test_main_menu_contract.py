from types import SimpleNamespace

from bot.keyboards.main_menu import main_menu_kb
from bot.ui.main_menu import render_main_menu
from bot.ui.navigation_v2 import render_create_hub, render_more_hub


def callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_v2_main_menu_has_mini_app_and_six_primary_entrypoints():
    ctx = SimpleNamespace(balance=100, active_image_session=None, is_admin=False)
    markup = render_main_menu(ctx).reply_markup

    assert markup.inline_keyboard[0][0].web_app is not None
    assert markup.inline_keyboard[0][0].web_app.url.endswith("/app")
    assert callbacks(markup) == [
        "menu:create",
        "menu:assistant",
        "menu:history",
        "menu:feed",
        "menu:balance",
        "menu:more",
    ]
    assert labels(markup) == [
        "📱 Открыть APIX",
        "✨ Создать",
        "🤖 AI-ассистент",
        "📂 Мои работы",
        "🔥 Лента",
        "💎 Баланс · 100",
        "☰ Ещё",
    ]


def test_legacy_builder_matches_v2_home_callbacks():
    ctx = SimpleNamespace(balance=100, active_image_session=None, is_admin=False)
    assert callbacks(render_main_menu(ctx).reply_markup) == callbacks(
        main_menu_kb(balance=100, has_active_image_session=False, is_admin=False)
    )


def test_v2_main_menu_keeps_secondary_features_off_home_screen():
    ctx = SimpleNamespace(balance=100, active_image_session=None, is_admin=False)
    cb = callbacks(render_main_menu(ctx).reply_markup)

    assert "menu:video" not in cb
    assert "menu:music" not in cb
    assert "menu:prompts" not in cb
    assert "menu:referral" not in cb
    assert "menu:help" not in cb
    assert "menu:topup" not in cb
    assert "menu:mj" not in cb
    assert "menu:settings" not in cb


def test_v2_create_hub_preserves_all_creation_entrypoints():
    cb = callbacks(render_create_hub(lang="ru", is_admin=False).reply_markup)
    assert cb == ["menu:image", "menu:video", "menu:music", "menu:assistant", "menu:main"]

    admin_cb = callbacks(render_create_hub(lang="ru", is_admin=True).reply_markup)
    assert "menu:mj" in admin_cb


def test_v2_more_hub_preserves_secondary_features():
    cb = callbacks(render_more_hub(lang="ru", is_admin=False).reply_markup)
    assert cb == ["menu:prompts", "menu:referral", "menu:settings", "menu:help", "menu:main"]

    admin_cb = callbacks(render_more_hub(lang="ru", is_admin=True).reply_markup)
    assert "menu:admin" in admin_cb


def test_v2_main_menu_preserves_active_work_shortcuts():
    ctx = SimpleNamespace(
        balance=100,
        active_image_session=SimpleNamespace(
            model="nano-banana-2",
            quality="high",
            aspect_ratio="1:1",
            count=2,
        ),
        is_admin=False,
    )
    cb = callbacks(render_main_menu(ctx).reply_markup)
    assert cb[:2] == ["menu:image", "img_session:new"]
    assert "menu:create" in cb
    assert "menu:history" in cb
