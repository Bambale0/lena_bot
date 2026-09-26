from types import SimpleNamespace

from bot.keyboards.main import get_main_menu_keyboard
from bot.keyboards.main_menu import main_menu_kb
from bot.ui.image_menu import render_image_advanced_menu, render_image_scenarios
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


def test_v2_main_menu_has_mini_app_and_topup_entrypoint():
    ctx = SimpleNamespace(balance=100, active_image_session=None, is_admin=False)
    screen = render_main_menu(ctx)
    markup = screen.reply_markup

    assert markup.inline_keyboard[0][0].web_app is not None
    assert markup.inline_keyboard[0][0].web_app.url.endswith("/app")
    assert callbacks(markup) == [
        "menu:create",
        "menu:assistant",
        "menu:history",
        "menu:feed",
        "menu:trends",
        "menu:pinterest",
        "menu:topup",
        "menu:more",
    ]
    assert labels(markup) == [
        "😊 Приложение",
        "✨ Создать",
        "🤖 AI-ассистент",
        "📂 Мои работы",
        "🔥 Лента идей",
        "👑 Тренды",
        "📌 Pinterest",
        "💳 Пополнить",
        "☰ Ещё",
    ]
    assert "Создавай изображения" in screen.text
    assert "Точную стоимость покажем до запуска" in screen.text
    assert "Приложение" in screen.text


def test_legacy_builder_opens_same_topup_flow():
    ctx = SimpleNamespace(balance=100, active_image_session=None, is_admin=False)
    active = callbacks(render_main_menu(ctx).reply_markup)
    legacy = callbacks(main_menu_kb(balance=100, has_active_image_session=False, is_admin=False))
    assert "menu:topup" in active
    assert "menu:topup" in legacy
    assert "menu:balance" not in active
    assert "menu:balance" not in legacy


def test_english_main_menu_opens_topup():
    ctx = SimpleNamespace(balance=100, active_image_session=None, is_admin=False)
    markup = render_main_menu(ctx, lang="en").reply_markup
    assert "💳 Top up" in labels(markup)
    assert "menu:topup" in callbacks(markup)


def test_older_main_menu_builder_opens_topup():
    markup = get_main_menu_keyboard(balance=100)
    assert "💳 Пополнить" in labels(markup)
    assert "menu:topup" in callbacks(markup)
    assert "menu:balance" not in callbacks(markup)


def test_v2_main_menu_keeps_secondary_features_off_home_screen():
    ctx = SimpleNamespace(balance=100, active_image_session=None, is_admin=False)
    cb = callbacks(render_main_menu(ctx).reply_markup)

    assert "menu:video" not in cb
    assert "menu:music" not in cb
    assert "menu:prompts" not in cb
    assert "menu:referral" not in cb
    assert "menu:help" not in cb
    assert "menu:balance" not in cb
    assert "menu:mj" not in cb
    assert "menu:settings" not in cb


def test_v2_create_hub_preserves_all_creation_entrypoints_and_explains_them():
    screen = render_create_hub(lang="ru", is_admin=False)
    cb = callbacks(screen.reply_markup)
    assert cb == [
        "menu:image",
        "menu:video",
        "img:photo2prompt",
        "vid:video2prompt",
        "menu:music",
        "menu:assistant",
        "menu:main",
    ]
    assert "карточки товаров" in screen.text
    assert "Промпт по фото" in screen.text
    assert "Промпт по видео" in screen.text
    assert "оживление фото" in screen.text
    assert "только задумка" in screen.text

    admin_cb = callbacks(render_create_hub(lang="ru", is_admin=True).reply_markup)
    assert "menu:mj" in admin_cb

    genjutsu_cb = callbacks(
        render_create_hub(lang="ru", is_admin=False, show_genjutsu=True).reply_markup
    )
    assert "menu:genjutsu" in genjutsu_cb
    genjutsu_screen = render_create_hub(lang="ru", is_admin=False, show_genjutsu=True)
    assert "Genjutsu" in genjutsu_screen.text


def test_v2_more_hub_preserves_secondary_features_and_explains_them():
    screen = render_more_hub(lang="ru", is_admin=False)
    cb = callbacks(screen.reply_markup)
    assert cb == ["menu:prompts", "menu:referral", "menu:settings", "menu:help", "menu:main"]
    assert "Готовые идеи" in screen.text
    assert "комиссию" in screen.text
    assert "Приложение также доступно" in screen.text

    admin_cb = callbacks(render_more_hub(lang="ru", is_admin=True).reply_markup)
    assert "menu:admin" in admin_cb


def test_image_entry_keeps_photo_prompt_visible():
    screen = render_image_scenarios()
    assert "Можно сразу отправлять" in screen.text
    assert "APIX сам выберет" in screen.text
    assert "Промпт по фото" in screen.text
    assert callbacks(screen.reply_markup) == [
        "img_v2:ratio",
        "img_v2:quality",
        "img_v2:refs",
        "img_menu:advanced",
        "img:photo2prompt",
        "vid:video2prompt",
        "menu:create",
    ]


def test_image_advanced_mode_warns_and_guides_model_choice():
    screen = render_image_advanced_menu([])
    assert "Экспертный выбор модели" in screen.text
    assert "Выбирай конкретную нейросеть" in screen.text
    assert "Nano Banana" in screen.text
    assert "Цена указана на кнопке" in screen.text


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
    screen = render_main_menu(ctx)
    cb = callbacks(screen.reply_markup)
    assert cb[:2] == ["img_session:continue", "img_session:new"]
    assert "menu:create" in cb
    assert "menu:history" in cb
    assert "активная серия" in screen.text
    assert "Nano Banana 2" in screen.text
