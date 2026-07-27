from types import SimpleNamespace

from bot.handlers.image_wizard_v2 import _composer_screen, _quality_choice_kb, _quick_flow_kb, _ratio_choice_kb
from bot.ui.image_menu import render_image_scenarios


def _texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_image_entry_is_task_first_not_model_first():
    screen = render_image_scenarios()
    texts = _texts(screen.reply_markup)
    callbacks = _callbacks(screen.reply_markup)

    assert "📐 Формат" in texts
    assert "💎 Качество" in texts
    assert "📎 Референсы" in texts
    assert "🧠 Сменить модель" in texts
    assert "✅ Продолжить" not in texts
    assert "img_v2:ratio" in callbacks
    assert "img_v2:quality" in callbacks
    assert "img_menu:advanced" in callbacks
    assert "Можно сразу отправлять" in screen.text
    assert "APIX сам выберет подходящий внутренний режим" in screen.text


def test_image_entry_continue_appears_after_params_changed():
    screen = _composer_screen({"image_params_changed": True})
    assert "✅ Продолжить" in _texts(screen.reply_markup)


def test_selected_model_uses_same_task_first_composer():
    screen = _composer_screen({
        "model_key": "gpt-image-2-text-to-image",
        "aspect_ratio": "1:1",
        "quality": "basic",
    })
    texts = _texts(screen.reply_markup)
    callbacks = _callbacks(screen.reply_markup)

    assert "GPT Image 2" in screen.text
    assert "Можно сразу отправлять" in screen.text
    assert "APIX сам выберет подходящий внутренний режим" in screen.text
    assert "📐 Формат" in texts
    assert "💎 Качество" in texts
    assert "📎 Референсы" in texts
    assert "🧠 Сменить модель" in texts
    assert "✅ Продолжить" not in texts
    assert "img_v2:ratio" in callbacks
    assert "img_v2:quality" in callbacks


def test_ratio_button_opens_explicit_choice_keyboard():
    markup = _ratio_choice_kb("gpt-image-2-text-to-image", "1:1")
    texts = _texts(markup)
    callbacks = _callbacks(markup)

    assert "✅ 1:1" in texts
    assert "← Назад" in texts
    assert "img_v2:ratio:set:1:1" in callbacks
    assert "img_v2:back" in callbacks


def test_quality_button_opens_explicit_choice_keyboard():
    markup = _quality_choice_kb("seedream/5-pro-text-to-image", "basic")
    texts = _texts(markup)
    callbacks = _callbacks(markup)

    assert any(text.startswith("✅ ") for text in texts)
    assert "← Назад" in texts
    assert "img_v2:quality:set:basic" in callbacks
    assert "img_v2:back" in callbacks


def test_quick_text_flow_keeps_expert_features_optional():
    markup = _quick_flow_kb(edit=False)
    texts = _texts(markup)
    callbacks = _callbacks(markup)

    assert "📎 Добавить фото" in texts
    assert "🧠 Другая модель" in texts
    assert "img_v2:add_reference" in callbacks
    assert "img_menu:advanced" in callbacks


def test_edit_flow_does_not_force_user_to_choose_edit_endpoint():
    markup = _quick_flow_kb(edit=True)
    texts = _texts(markup)

    assert "🧠 Другая модель" in texts
    assert all("Edit" not in text for text in texts)
