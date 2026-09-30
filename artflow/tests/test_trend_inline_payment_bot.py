from types import SimpleNamespace

from bot.handlers import trends


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_direct_image_trend_repeat_button_shows_exact_price() -> None:
    prompt = SimpleNamespace(id=101)
    markup = trends._catalog_kb(
        prompt,
        index=0,
        total=1,
        is_admin=False,
        repeat_cost=12.5,
    )

    repeat = next(button for button in _buttons(markup) if button.callback_data == "trends:use:101")
    assert repeat.text == "🔥 Повторить · 12.5 💋"


def test_insufficient_direct_trend_offer_has_one_tap_topup() -> None:
    prompt = SimpleNamespace(title="Кинопортрет")
    text = trends._insufficient_repeat_text(prompt, price=20, balance=1)
    markup = trends._insufficient_repeat_kb()

    assert "Повтор: <b>20 💋</b>" in text
    assert "Не хватает: <b>19 💋</b>" in text
    callbacks = [button.callback_data for button in _buttons(markup)]
    assert callbacks[:2] == ["menu:topup", "menu:trends"]
