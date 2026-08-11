from __future__ import annotations

from types import SimpleNamespace

from bot.handlers import image_gen
from bot.handlers.start import _help_text
from bot.keyboards.main_menu import back_to_menu_kb, main_menu_kb
from bot.keyboards.models import (
    IMAGE_CAPS,
    after_generation_kb,
    image_quality_kb,
    image_session_kb,
    image_style_edit_kb,
    public_prompt_text,
    video_model_groups_kb,
    video_models_kb,
    video_params_kb,
)
from bot.keyboards.payment import rub_methods_kb, topup_kb
from bot.keyboards.prompts import prompt_use_model_kb
from bot.ui.image_menu import render_active_image_session
from bot.ui.main_menu import render_main_menu
from core.config import settings
from db.models import GenerationType, ModelCost


def flatten_buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_main_menu_keyboard_keeps_core_buttons() -> None:
    buttons = flatten_buttons(main_menu_kb(balance=100, has_active_image_session=True, is_admin=True))
    texts = [button.text for button in buttons]
    assert "🎨 Изображение" in texts
    assert "📚 Библиотека" in texts
    assert "👑 Админ" in texts


def test_main_menus_show_webapp_button_at_top() -> None:
    context = SimpleNamespace(balance=100, active_image_session=None, is_admin=False)
    legacy_markup = main_menu_kb(balance=100)
    ui_markup = render_main_menu(context).reply_markup

    assert legacy_markup.inline_keyboard[0][0].web_app is not None
    assert ui_markup.inline_keyboard[0][0].web_app is not None

    assert all(button.web_app is None for button in flatten_buttons(legacy_markup)[1:])
    assert all(button.web_app is None for button in flatten_buttons(ui_markup)[1:])


def test_main_menu_keyboard_uses_public_web_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WEB_PUBLIC_URL", "https://miniapp.example", raising=False)

    markup = main_menu_kb(balance=100)

    assert markup.inline_keyboard[0][0].web_app.url == "https://miniapp.example/app?v=1778285569"


def test_render_main_menu_uses_public_web_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WEB_PUBLIC_URL", "https://miniapp.example", raising=False)
    context = SimpleNamespace(balance=100, active_image_session=None, is_admin=False)

    render = render_main_menu(context)

    assert render.reply_markup.inline_keyboard[0][0].web_app.url == "https://miniapp.example/app?v=1778285569"


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


def test_wan_image_quality_defaults_to_2k_and_keeps_manual_4k() -> None:
    assert IMAGE_CAPS["wan/2-7-image"]["quality_options"][0][0] == "2K"
    assert IMAGE_CAPS["wan/2-7-image-pro"]["quality_options"][0][0] == "2K"

    buttons = flatten_buttons(image_quality_kb("wan/2-7-image-pro"))
    assert [button.text for button in buttons[:2]] == ["2K", "4K"]


def test_render_active_image_session_uses_result_actions_when_last_generation_exists() -> None:
    session = SimpleNamespace(
        model="wan/2-7-image-pro",
        aspect_ratio=None,
        quality="4K",
        count=2,
        reference_file_ids='["face_ref", "outfit_ref"]',
        reference_url=None,
        reference_file_id=None,
        last_generation_id=123,
    )
    generation = SimpleNamespace(id=123, prompt="own prompt", source_feed_gen_id=None)

    buttons = flatten_buttons(render_active_image_session(session, active_generation=generation).reply_markup)
    texts = {button.text for button in buttons}

    assert "📋 Скопировать промпт" in texts
    assert "📤 В ленту" in texts
    assert "📚 В библиотеку" in texts


def test_render_active_image_session_hides_result_actions_for_feed_derivative() -> None:
    session = SimpleNamespace(
        model="wan/2-7-image-pro",
        aspect_ratio=None,
        quality="4K",
        count=2,
        reference_file_ids='["face_ref", "outfit_ref"]',
        reference_url=None,
        reference_file_id=None,
        last_generation_id=123,
    )
    generation = SimpleNamespace(id=123, prompt="hidden prompt", source_feed_gen_id=77)

    buttons = flatten_buttons(render_active_image_session(session, active_generation=generation).reply_markup)
    texts = {button.text for button in buttons}

    assert "📋 Скопировать промпт" not in texts
    assert "📤 В ленту" not in texts
    assert "📚 В библиотеку" not in texts


def test_render_active_image_session_can_show_actions_for_own_feed_source() -> None:
    session = SimpleNamespace(
        model="wan/2-7-image-pro",
        aspect_ratio=None,
        quality="4K",
        count=2,
        reference_file_ids='["face_ref", "outfit_ref"]',
        reference_url=None,
        reference_file_id=None,
        last_generation_id=123,
    )
    generation = SimpleNamespace(id=123, prompt="own prompt", source_feed_gen_id=77)

    buttons = flatten_buttons(
        render_active_image_session(
            session,
            active_generation=generation,
            prompt_actions_allowed=True,
        ).reply_markup
    )
    texts = {button.text for button in buttons}

    assert "📋 Скопировать промпт" in texts
    assert "📤 В ленту" in texts
    assert "📚 В библиотеку" in texts


def test_render_active_image_session_hides_prompt_copy_for_repeat_result() -> None:
    session = SimpleNamespace(
        model="wan/2-7-image-pro",
        aspect_ratio=None,
        quality="4K",
        count=2,
        reference_file_ids='["face_ref", "outfit_ref"]',
        reference_url=None,
        reference_file_id=None,
        last_generation_id=123,
    )
    generation = SimpleNamespace(id=123, prompt="repeat prompt", source_feed_gen_id=None, action_type="repeat")

    buttons = flatten_buttons(render_active_image_session(session, active_generation=generation).reply_markup)
    texts = {button.text for button in buttons}

    assert "📋 Скопировать промпт" not in texts
    assert "📋 Показать промпт" not in texts
    assert "📤 В ленту" in texts
    assert "📚 В библиотеку" in texts


def test_render_active_image_session_hides_prompt_copy_for_stringified_repeat_result() -> None:
    session = SimpleNamespace(
        model="wan/2-7-image-pro",
        aspect_ratio=None,
        quality="4K",
        count=2,
        reference_file_ids='["face_ref", "outfit_ref"]',
        reference_url=None,
        reference_file_id=None,
        last_generation_id=123,
    )
    generation = SimpleNamespace(
        id=123,
        prompt="repeat prompt",
        source_feed_gen_id=None,
        action_type="ImageGenerationAction.repeat",
    )

    buttons = flatten_buttons(render_active_image_session(session, active_generation=generation).reply_markup)
    texts = {button.text for button in buttons}

    assert "📋 Скопировать промпт" not in texts
    assert "📋 Показать промпт" not in texts
    assert "📤 В ленту" in texts
    assert "📚 В библиотеку" in texts


def test_repeat_setup_keyboard_exposes_model_switch() -> None:
    image_session = SimpleNamespace(
        id=77,
        model="seedream/5-pro-text-to-image",
        mode="text",
    )

    buttons = flatten_buttons(image_gen._repeat_setup_kb(image_session))
    callbacks = {button.callback_data for button in buttons if button.callback_data}

    assert "img_repeat:model:77" in callbacks


def test_render_active_image_session_without_result_keeps_basic_active_actions() -> None:
    session = SimpleNamespace(
        model="wan/2-7-image-pro",
        aspect_ratio=None,
        quality="4K",
        count=2,
        reference_file_ids='["face_ref", "outfit_ref"]',
        reference_url=None,
        reference_file_id=None,
        last_generation_id=None,
    )

    buttons = flatten_buttons(render_active_image_session(session).reply_markup)
    texts = {button.text for button in buttons}

    assert "✨ Ремикс" in texts
    assert "📤 В ленту" not in texts
    assert "📚 В библиотеку" not in texts


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


def test_prompt_use_model_kb_reference_only_filters_text_models() -> None:
    costs = [
        ModelCost(
            model_key="gpt-image-2-text-to-image",
            display_name="GPT Image 2",
            credits=2,
            gen_type=GenerationType.image,
            is_active=True,
        ),
        ModelCost(
            model_key="gpt-image-2-image-to-image",
            display_name="GPT Image 2 Edit",
            credits=2,
            gen_type=GenerationType.image,
            is_active=True,
        ),
    ]

    buttons = flatten_buttons(prompt_use_model_kb(42, costs, reference_only=True))
    callbacks = {button.callback_data for button in buttons}

    assert "prompt_pick_model:42:gpt-image-2-text-to-image" not in callbacks
    assert "prompt_pick_model:42:gpt-image-2-image-to-image" in callbacks


def test_video_menu_has_gemini_omni_group_and_tools() -> None:
    group_buttons = flatten_buttons(video_model_groups_kb())
    assert any(button.callback_data == "vid_group:omni" for button in group_buttons)

    costs = [
        SimpleNamespace(
            model_key="gemini-omni-video",
            display_name="Gemini Omni",
            credits=90,
            gen_type=GenerationType.video,
        )
    ]
    buttons = flatten_buttons(video_models_kb(costs, "omni"))
    callbacks = {button.callback_data for button in buttons}
    assert "vid_model:gemini-omni-video" in callbacks
    assert "vid_omni_audio" in callbacks
    assert "vid_omni_character" in callbacks


def test_video_params_kb_shows_gemini_omni_controls() -> None:
    buttons = flatten_buttons(
        video_params_kb("gemini-omni-video", 4, "16:9", "720p", selected_mode="video")
    )
    callbacks = {button.callback_data for button in buttons}
    assert "vpar_omni:audio" in callbacks
    assert "vpar_omni:character" in callbacks
    assert "vpar_omni:seed" in callbacks
    assert all(not button.callback_data.startswith("vpar_dur:") for button in buttons)
    assert "vpar_res:1080p" not in callbacks
    assert "vpar_res:4k" not in callbacks
    assert any(button.text == "🎙️ Audio ID" for button in buttons)


def test_image_session_keyboard_keeps_library_button_and_style_edit() -> None:
    buttons = flatten_buttons(image_session_kb(123))
    by_text = {button.text: button.callback_data for button in buttons}
    assert by_text["📚 В библиотеку"] == "gen:library:123"
    assert by_text["💅 Изменить образ"] == "img_session:style:123"


def test_image_session_keyboard_can_copy_short_prompt() -> None:
    prompt = "короткий промпт"
    buttons = flatten_buttons(image_session_kb(123, prompt=prompt))
    copy_button = next(button for button in buttons if button.text == "📋 Скопировать промпт")
    assert copy_button.copy_text.text == prompt


def test_image_session_keyboard_keeps_actions_when_prompt_is_too_long_for_copy_button() -> None:
    prompt = "очень длинный промпт " * 30
    buttons = flatten_buttons(image_session_kb(123, prompt=prompt))
    by_text = {button.text: button for button in buttons}
    assert by_text["📋 Показать промпт"].callback_data == "gen:prompt:123"
    assert by_text["📤 В ленту"].callback_data == "gen:share:123"
    assert by_text["📚 В библиотеку"].callback_data == "gen:library:123"


def test_image_session_keyboard_hides_prompt_public_actions_for_feed_derivative() -> None:
    prompt = "private feed prompt"
    buttons = flatten_buttons(
        image_session_kb(
            123,
            prompt=prompt,
            allow_publish=False,
            allow_copy_prompt=False,
        )
    )
    texts = {button.text for button in buttons}
    assert "📋 Скопировать промпт" not in texts
    assert "📤 В ленту" not in texts
    assert "📚 В библиотеку" not in texts


def test_public_prompt_text_hides_service_style_wrapper() -> None:
    prompt = (
        "Edit the reference image. Change ONLY the main person's hair color to: розовый. "
        "Keep the hairstyle, face, skin, clothing, body, pose, background, cars, vehicles, and all other objects unchanged. "
        "Do not recolor anything except the hair."
    )
    assert public_prompt_text(prompt) == "розовый"


def test_image_style_edit_keyboard_covers_requested_appearance_changes() -> None:
    buttons = flatten_buttons(image_style_edit_kb(123))
    callbacks = {button.callback_data for button in buttons}
    assert {
        "img_style:clothes:123",
        "img_style:haircut:123",
        "img_style:hair_color:123",
        "img_style:nails:123",
    }.issubset(callbacks)


def test_after_generation_keyboard_uses_library_label() -> None:
    buttons = flatten_buttons(after_generation_kb(123, "image"))
    by_text = {button.text: button.callback_data for button in buttons}
    assert by_text["📚 В библиотеку"] == "gen:library:123"


def test_after_generation_keyboard_keeps_actions_when_prompt_is_too_long_for_copy_button() -> None:
    prompt = "очень длинный видео промпт " * 30
    buttons = flatten_buttons(after_generation_kb(123, "video", prompt=prompt))
    by_text = {button.text: button for button in buttons}
    assert by_text["📋 Показать промпт"].callback_data == "gen:prompt:123"
    assert by_text["📤 В ленту"].callback_data == "gen:share:123"
    assert by_text["📚 В библиотеку"].callback_data == "gen:library:123"
    callbacks = {button.callback_data for button in buttons if button.callback_data}
    assert "reprompt:video:123" in callbacks
    assert "reparams:video:123" in callbacks


def test_after_generation_keyboard_can_hide_copy_and_publish_actions() -> None:
    buttons = flatten_buttons(
        after_generation_kb(
            123,
            "video",
            prompt="private feed prompt",
            allow_publish=False,
            allow_copy_prompt=False,
        )
    )
    texts = {button.text for button in buttons}
    assert "📋 Скопировать промпт" not in texts
    assert "📤 В ленту" not in texts
    assert "📚 В библиотеку" not in texts


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


def test_rub_methods_keyboard_shows_lava_when_configured(monkeypatch) -> None:
    monkeypatch.setattr("bot.keyboards.payment.settings.LAVA_API_KEY", "lava", raising=False)
    monkeypatch.setenv("LAVA_OFFER_ID_CREDITS_100", "offer-1")

    buttons = flatten_buttons(rub_methods_kb())

    assert any(button.callback_data == "topup:lava" for button in buttons)
