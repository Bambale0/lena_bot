from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.config import settings
from payments import tribute


@pytest.fixture(autouse=True)
def payment_configuration(monkeypatch):
    for key in ("TBANK_TERMINAL_KEY", "TBANK_PASSWORD", "CRYPTOBOT_TOKEN", "TRIBUTE_API_KEY", "LAVA_API_KEY"):
        monkeypatch.setattr(settings, key, "")
    monkeypatch.setattr(type(settings), "lava_offer_id_for_plan", lambda self, key: "")


def plan(key="custom", **changes):
    return SimpleNamespace(key=key, price_rub=180.0, is_active=True, **changes)


def test_plan_methods_require_that_plans_own_tribute_and_lava_mapping(monkeypatch):
    from payments.checkout_options import payment_options_for_plan

    monkeypatch.setattr(settings, "TRIBUTE_API_KEY", "test")
    monkeypatch.setattr(settings, "LAVA_API_KEY", "test")
    monkeypatch.setattr(type(settings), "lava_offer_id_for_plan", lambda self, key: "offer" if key == "mapped" else "")
    assert payment_options_for_plan(plan()) == []
    assert payment_options_for_plan(plan("mapped")) == [
        {"provider": "lava", "amount": None, "currency": "RUB"},
    ]


def test_options_disclose_actual_tbank_crypto_and_tribute_currencies(monkeypatch):
    from payments.checkout_options import crypto_amount_usdt, payment_options_for_plan

    for key in ("TBANK_TERMINAL_KEY", "TBANK_PASSWORD", "CRYPTOBOT_TOKEN", "TRIBUTE_API_KEY"):
        monkeypatch.setattr(settings, key, "test")
    product = tribute.digital_product_for_plan("credits_15")
    assert product is not None
    assert payment_options_for_plan(plan("credits_15")) == [
        {"provider": "tbank", "amount": 180.0, "currency": "RUB"},
        {"provider": "crypto", "amount": 2.0, "currency": "USDT"},
        {"provider": "tribute", "amount": product.amount_major, "currency": "USD"},
    ]
    assert crypto_amount_usdt(100) == 1.11


def test_disabled_and_inactive_plans_have_no_checkout_options(monkeypatch):
    from payments.checkout_options import payment_options_for_plan

    assert payment_options_for_plan(plan("credits_15")) == []
    monkeypatch.setattr(settings, "CRYPTOBOT_TOKEN", "test")
    inactive = plan()
    inactive.is_active = False
    assert payment_options_for_plan(inactive) == []


@pytest.mark.parametrize("key", ["custom", "credits_15", "mapped"])
def test_available_providers_match_text_bot_plan_buttons(key, monkeypatch):
    from bot.keyboards.payment import plan_payment_methods_kb
    from payments.checkout_options import payment_options_for_plan

    for setting in ("TBANK_TERMINAL_KEY", "TBANK_PASSWORD", "CRYPTOBOT_TOKEN", "TRIBUTE_API_KEY", "LAVA_API_KEY"):
        monkeypatch.setattr(settings, setting, "test")
    monkeypatch.setattr(type(settings), "lava_offer_id_for_plan", lambda self, key: "offer" if key == "mapped" else "")
    monkeypatch.setattr(type(settings), "lava_is_enabled", lambda self: True)
    package = plan(key)
    callbacks = {
        button.callback_data for row in plan_payment_methods_kb(package).inline_keyboard for button in row
    }
    expected = {
        provider for provider, callback in {
            "tbank": f"topup:rub:{key}", "crypto": f"topup:crypto_plan:{key}",
            "tribute": f"topup:tribute_plan:{key}", "lava": f"topup:lava_plan:{key}",
        }.items() if callback in callbacks
    }
    assert {option["provider"] for option in payment_options_for_plan(package)} == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,mapped_key,amount,currency", [
    ("tribute", "credits_15", 2.0, "USD"),
    ("lava", "lava_mapped", None, "RUB"),
])
async def test_feed_quote_skips_smaller_unpurchasable_plan_and_discloses_mapped_checkout(
    provider, mapped_key, amount, currency, monkeypatch,
):
    from api import miniapp_routes

    monkeypatch.setattr(settings, "TRIBUTE_API_KEY", "test" if provider == "tribute" else "")
    monkeypatch.setattr(settings, "LAVA_API_KEY", "test" if provider == "lava" else "")
    monkeypatch.setattr(type(settings), "lava_offer_id_for_plan", lambda self, key: "offer" if key == "lava_mapped" else "")
    source = SimpleNamespace(id=88, model="nano-banana-2", gen_type="image", prompt="hidden author prompt",
                             result_url="https://example.test/source.png", result_urls=None)
    monkeypatch.setattr(miniapp_routes.repo, "get_public_feed_generation", AsyncMock(return_value=source))
    monkeypatch.setattr(miniapp_routes.repo, "resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=5, is_active=True)))
    monkeypatch.setattr(miniapp_routes.repo, "has_unlimited_image_model", AsyncMock(return_value=False))
    packages = AsyncMock(return_value=[plan("unmapped", credits=6, label="Unmapped"), plan(mapped_key, credits=15, label="Mapped")])
    monkeypatch.setattr(miniapp_routes.repo, "get_active_price_plans", packages)
    charge = AsyncMock()
    transaction = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "charge_image_generation", charge)
    monkeypatch.setattr(miniapp_routes.repo, "create_transaction", transaction)

    result = await miniapp_routes.quote_feed_remix(
        88, miniapp_routes.FeedRemixRequest(model="nano-banana-2", quality="2K"),
        session=AsyncMock(), user=SimpleNamespace(id=42, credits=0),
    )
    assert result["recommended_plan"]["key"] == mapped_key
    assert result["recommended_plan"]["payment_options"] == [
        {"provider": provider, "amount": amount, "currency": currency},
    ]
    assert result["deficit_credits"] == 5
    assert "hidden author prompt" not in str(result)
    charge.assert_not_awaited()
    transaction.assert_not_awaited()

    packages.return_value = [plan("unmapped", credits=6, label="Unmapped")]
    result = await miniapp_routes.quote_feed_remix(
        88, miniapp_routes.FeedRemixRequest(model="nano-banana-2", quality="2K"),
        session=AsyncMock(), user=SimpleNamespace(id=42, credits=0),
    )
    assert result["recommended_plan"] is None
    assert result["can_run"] is False
    charge.assert_not_awaited()
    transaction.assert_not_awaited()


@pytest.mark.parametrize("lang,disclosure", [("ru", "Сумма в ₽ на странице оплаты"), ("en", "RUB amount at checkout")])
@pytest.mark.parametrize("legacy_currency", ["rub", "usd"])
def test_bot_lava_plan_list_discloses_provider_amount(lang, disclosure, legacy_currency):
    from bot.keyboards.payment import lava_plans_kb

    package = plan("mapped", credits=15, label="Plan")
    texts = [button.text for row in lava_plans_kb([package], lang=lang, currency=legacy_currency).inline_keyboard for button in row]
    assert disclosure in texts[0]
    assert "180" not in texts[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("lang,disclosure", [("ru", "Сумма в ₽ на странице оплаты"), ("en", "RUB amount at checkout")])
async def test_bot_lava_invoice_does_not_claim_db_price_is_provider_charge(lang, disclosure, monkeypatch):
    from bot.handlers import payment

    package = plan("mapped", credits=15, label="Plan")
    monkeypatch.setattr(type(settings), "lava_offer_id_for_plan", lambda self, key: "offer")
    monkeypatch.setattr(payment.repo, "get_price_plan_by_key", AsyncMock(return_value=package))
    create_invoice = AsyncMock(return_value=SimpleNamespace(invoice_id="invoice", payment_url="https://example.test/pay"))
    monkeypatch.setattr(payment.lava, "create_invoice", create_invoice)
    transaction = AsyncMock()
    monkeypatch.setattr(payment.repo, "create_transaction", transaction)
    call = SimpleNamespace(data="topup:lava_plan:mapped", message=SimpleNamespace(edit_text=AsyncMock()), answer=AsyncMock())

    await payment.cb_topup_lava_plan(call, AsyncMock(), SimpleNamespace(id=7, language=lang))

    text = call.message.edit_text.await_args.args[0]
    assert disclosure in text
    assert "180" not in text
    create_invoice.assert_awaited_once_with(package, 7)
    assert transaction.await_args.kwargs["amount_rub"] == 180.0
