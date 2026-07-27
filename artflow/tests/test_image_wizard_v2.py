from types import SimpleNamespace

from bot.handlers.image_wizard_v2 import _quick_flow_kb
from bot.ui.image_menu import render_image_scenarios


def _texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_image_entry_is_task_first_not_model_first():
    screen = render_image_scenarios()
    texts = _texts(screen.reply_markup)
    callbacks = _callbacks(screen.reply_markup)

    assert "✨ Создать с нуля" in texts
    assert "🪄 Изменить фото" in texts
    assert "📸 Фото → промпт" in texts
    assert "🧠 Выбрать модель" in texts
    assert "img_v2:text" in callbacks
    assert "img_v2:edit" in callbacks
    assert "img_menu:advanced" in callbacks
    assert "Выбери только результат" in screen.text


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
