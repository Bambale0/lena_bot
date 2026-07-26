from types import SimpleNamespace

from bot.ui.main_menu import render_main_menu


def callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def labels(markup):
    return [
        button.text
        for row in markup.inline_keyboard
        for button in row
    ]


def test_v2_main_menu_has_six_primary_entrypoints():
    ctx = SimpleNamespace(
        balance=100,
        active_image_session=None,
        is_admin=False,
    )

    markup = render_main_menu(ctx).reply_markup

    assert callbacks(markup) == [
        "menu:image",
        "menu:assistant",
        "menu:history",
        "menu:feed",
        "menu:balance",
        "menu:settings",
    ]
    assert labels(markup) == [
        "✨ Создать",
        "🤖 AI-ассистент",
        "📂 Мои работы",
        "🔥 Лента",
        "💎 Баланс · 100",
        "☰ Ещё",
    ]


def test_v2_main_menu_keeps_secondary_features_off_home_screen():
    ctx = SimpleNamespace(
        balance=100,
        active_image_session=None,
        is_admin=False,
    )

    cb = callbacks(render_main_menu(ctx).reply_markup)

    assert "menu:video" not in cb
    assert "menu:music" not in cb
    assert "menu:prompts" not in cb
    assert "menu:referral" not in cb
    assert "menu:help" not in cb
    assert "menu:topup" not in cb
    assert "menu:mj" not in cb


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
    assert "menu:image" in cb
    assert "menu:history" in cb


def test_v2_admin_entrypoint_is_role_gated():
    user_ctx = SimpleNamespace(balance=100, active_image_session=None, is_admin=False)
    admin_ctx = SimpleNamespace(balance=100, active_image_session=None, is_admin=True)

    assert "menu:admin" not in callbacks(render_main_menu(user_ctx).reply_markup)
    assert callbacks(render_main_menu(admin_ctx).reply_markup)[-1] == "menu:admin"
