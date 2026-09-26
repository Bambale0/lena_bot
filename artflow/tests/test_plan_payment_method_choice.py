from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import payment
from bot.i18n import t
from bot.keyboards.payment import plan_payment_methods_kb, rub_methods_kb, topup_kb

ROOT = Path(__file__).resolve().parents[1]

# The RUB acquirer is an implementation detail. Users read its brand name on the
# payment button as "only this bank is accepted", so the copy advertises the rails.
# The bare "tbank" token is a provider key in code, not user-visible branding.
ACQUIRER_BRANDS = ("t-bank", "т-банк", "тбанк", "тинькофф")


def _texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def _enable_rub_only(monkeypatch) -> None:
    monkeypatch.setattr("bot.keyboards.payment.settings.TBANK_TERMINAL_KEY", "terminal", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.TBANK_PASSWORD", "password", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.TRIBUTE_API_KEY", "", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.CRYPTOBOT_TOKEN", "", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.LAVA_API_KEY", "", raising=False)


def _callbacks(markup) -> list[str | None]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_main_topup_package_routes_to_payment_method_choice(monkeypatch) -> None:
    plan = SimpleNamespace(label="Профи", credits=100, price_rub=1000.0, key="credits_100_999")
    monkeypatch.setattr("bot.keyboards.payment.settings.TRIBUTE_API_KEY", "tribute", raising=False)
    buttons = [button for row in topup_kb([plan]).inline_keyboard for button in row]
    assert buttons[0].callback_data == "topup:plan:credits_100_999"
    assert buttons[0].text == "💳 Профи — 100 💋 · 1000₽ | $12"


def test_plan_payment_methods_include_tbank_tribute_and_crypto_without_stars(monkeypatch) -> None:
    plan = SimpleNamespace(label="Профи", credits=100, price_rub=1000.0, key="credits_100_999")
    monkeypatch.setattr("bot.keyboards.payment.settings.TBANK_TERMINAL_KEY", "terminal", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.TBANK_PASSWORD", "password", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.TRIBUTE_API_KEY", "tribute", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.CRYPTOBOT_TOKEN", "crypto", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.LAVA_API_KEY", "", raising=False)

    markup = plan_payment_methods_kb(plan)
    callbacks = _callbacks(markup)
    texts = [button.text for row in markup.inline_keyboard for button in row]

    assert "topup:rub:credits_100_999" in callbacks
    assert "topup:tribute_plan:credits_100_999" in callbacks
    assert "topup:crypto_plan:credits_100_999" in callbacks
    assert all("stars" not in str(callback or "").lower() for callback in callbacks)
    assert any(text.startswith("💵 USD · $12") for text in texts)


@pytest.mark.asyncio
async def test_main_package_click_opens_method_choice_without_creating_tbank_invoice(monkeypatch) -> None:
    plan = SimpleNamespace(
        key="credits_100_999",
        label="Профи",
        credits=100.0,
        price_rub=1000.0,
        is_active=True,
    )
    message = SimpleNamespace(edit_text=AsyncMock())
    call = SimpleNamespace(data="topup:plan:credits_100_999", message=message, answer=AsyncMock())
    monkeypatch.setattr(payment.repo, "get_price_plan_by_key", AsyncMock(return_value=plan))
    monkeypatch.setattr("bot.keyboards.payment.settings.TBANK_TERMINAL_KEY", "terminal", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.TBANK_PASSWORD", "password", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.TRIBUTE_API_KEY", "tribute", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.CRYPTOBOT_TOKEN", "crypto", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.LAVA_API_KEY", "", raising=False)
    create_payment = AsyncMock()
    monkeypatch.setattr(payment.tbank, "create_payment", create_payment)

    await payment.cb_topup_plan_methods(call, AsyncMock(), SimpleNamespace(id=7, language="ru"))

    create_payment.assert_not_awaited()
    message.edit_text.assert_awaited_once()
    markup = message.edit_text.await_args.kwargs["reply_markup"]
    callbacks = _callbacks(markup)
    assert "topup:rub:credits_100_999" in callbacks
    assert "topup:tribute_plan:credits_100_999" in callbacks
    call.answer.assert_awaited_once()


def test_main_topup_embeds_usd_price_and_removes_currency_shortcuts(monkeypatch) -> None:
    plan = SimpleNamespace(label="Профи", credits=100, price_rub=1000.0, key="credits_100_999")
    monkeypatch.setattr("bot.keyboards.payment.settings.TRIBUTE_API_KEY", "tribute", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.CRYPTOBOT_TOKEN", "crypto", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.LAVA_API_KEY", "lava", raising=False)
    monkeypatch.setenv("LAVA_OFFER_ID_CREDITS_100", "offer-1")

    buttons = [button for row in topup_kb([plan]).inline_keyboard for button in row]
    callbacks = [button.callback_data for button in buttons]
    labels = [button.text for button in buttons]

    assert buttons[0].text == "💳 Профи — 100 💋 · 1000₽ | $12"
    assert "topup:tribute" not in callbacks
    assert "topup:rub" not in callbacks
    assert "topup:usd" not in callbacks
    assert "topup:crypto" in callbacks
    assert "topup:lava" in callbacks
    assert "💵 USD" not in labels
    assert "₽ Рубль" not in labels
    assert "💸 Lava" in labels


@pytest.mark.asyncio
async def test_legacy_usd_callback_routes_to_tribute_not_lava(monkeypatch) -> None:
    call = SimpleNamespace(data="topup:usd", message=SimpleNamespace(edit_text=AsyncMock()), answer=AsyncMock())
    db_user = SimpleNamespace(id=7, language="ru")
    tribute_handler = AsyncMock()
    monkeypatch.setattr(payment, "cb_topup_tribute", tribute_handler)

    await payment.cb_topup_usd(call, AsyncMock(), db_user)

    tribute_handler.assert_awaited_once()


def test_rub_payment_buttons_offer_card_and_sbp_without_acquirer_branding(monkeypatch) -> None:
    plan = SimpleNamespace(label="Профи", credits=100, price_rub=1000.0, key="credits_100_999")
    _enable_rub_only(monkeypatch)

    russian = _texts(plan_payment_methods_kb(plan, lang="ru")) + _texts(rub_methods_kb(lang="ru"))
    english = _texts(plan_payment_methods_kb(plan, lang="en")) + _texts(rub_methods_kb(lang="en"))

    assert "💳 Карта | СБП" in russian
    assert "💳 Card | SBP" in english
    for text in russian + english:
        assert not any(brand in text.lower() for brand in ACQUIRER_BRANDS), text


def test_topup_rub_copy_does_not_name_the_acquirer() -> None:
    assert t("topup_rub", "ru") == "💳 Карта | СБП"
    assert t("topup_rub", "en") == "💳 Card | SBP"

    for lang in ("ru", "en"):
        title = t("topup_tbank_title", lang)
        assert "СБП" in title or "SBP" in title
        assert not any(brand in title.lower() for brand in ACQUIRER_BRANDS), title


def test_billing_api_label_advertises_rails_not_acquirer(monkeypatch) -> None:
    from api.web import billing

    monkeypatch.setattr(billing.settings, "TBANK_TERMINAL_KEY", "terminal", raising=False)
    monkeypatch.setattr(billing.settings, "TBANK_PASSWORD", "password", raising=False)
    monkeypatch.setattr(billing.settings, "CRYPTOBOT_TOKEN", "", raising=False)
    monkeypatch.setattr(billing.settings, "TRIBUTE_API_KEY", "", raising=False)
    monkeypatch.setattr(billing.settings, "LAVA_API_KEY", "", raising=False)

    methods = billing.enabled_payment_methods()

    assert [item["key"] for item in methods] == ["tbank"]
    assert [item["label"] for item in methods] == ["Карта | СБП"]


def test_payment_surfaces_do_not_render_acquirer_branding() -> None:
    balance_sheet = (ROOT / "webapp/src/components/balance-sheet.tsx").read_text(encoding="utf-8")
    legacy_site = (ROOT / "webapp/src/main.jsx").read_text(encoding="utf-8")
    public_site = (ROOT / "landing/js/prototype-premium.js").read_text(encoding="utf-8")

    assert 'title: "Карта | СБП"' in balance_sheet
    assert "💳 Карта | СБП" in legacy_site
    assert 'tbank: "Карта | СБП"' in public_site

    for source in (balance_sheet, legacy_site, public_site):
        assert not any(brand in source.lower() for brand in ACQUIRER_BRANDS)
