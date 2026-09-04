from __future__ import annotations

from bot.legal_offer import MAX_OFFER_PAGE_CHARS, PUBLIC_OFFER_PAGES, PUBLIC_OFFER_TEXT


def _callbacks(markup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def _labels(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_public_offer_fits_telegram_pages_and_contains_approved_requisites():
    assert PUBLIC_OFFER_PAGES
    assert all(len(page) <= MAX_OFFER_PAGE_CHARS for page in PUBLIC_OFFER_PAGES)
    assert "Индивидуальный предприниматель Дудкин Дмитрий Александрович" in PUBLIC_OFFER_TEXT
    assert "ИНН: 790303276607" in PUBLIC_OFFER_TEXT
    assert "ОГРНИП: 326270000003817" in PUBLIC_OFFER_TEXT
    assert "Расчётный счёт: 40802810300009286175" in PUBLIC_OFFER_TEXT
    assert "АО «ТБанк»" in PUBLIC_OFFER_TEXT
    assert "БИК: 044525974" in PUBLIC_OFFER_TEXT
    assert "30101810145250000974" in PUBLIC_OFFER_TEXT
    assert "127287, г. Москва, ул. Хуторская 2-я, д. 38А, стр. 26" in PUBLIC_OFFER_TEXT


def test_public_offer_has_user_action_responsibility_clause_and_no_placeholders():
    assert "ОТВЕТСТВЕННОСТЬ ПОЛЬЗОВАТЕЛЯ" in PUBLIC_OFFER_TEXT
    assert "Пользователь самостоятельно несёт ответственность" in PUBLIC_OFFER_TEXT
    assert "Исполнитель не несёт ответственности за противоправные действия Пользователя" in PUBLIC_OFFER_TEXT
    assert "[ДОБАВИТЬ" not in PUBLIC_OFFER_TEXT
    assert "Адрес Исполнителя" not in PUBLIC_OFFER_TEXT
    assert "Орган, осуществивший государственную регистрацию" not in PUBLIC_OFFER_TEXT
    assert "E-mail для обращений" not in PUBLIC_OFFER_TEXT


def test_partner_screen_contains_public_offer_button_and_offer_has_navigation():
    from bot.handlers.balance import public_offer_kb, referral_screen_kb

    partner_markup = referral_screen_kb("ru")
    assert "referral:offer" in _callbacks(partner_markup)
    assert "📄 Публичная оферта" in _labels(partner_markup)

    first_page_markup = public_offer_kb(0, "ru")
    callbacks = _callbacks(first_page_markup)
    assert "referrals" in callbacks
    if len(PUBLIC_OFFER_PAGES) > 1:
        assert "referral:offer:1" in callbacks
