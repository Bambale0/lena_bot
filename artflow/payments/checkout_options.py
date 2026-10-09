"""Read-only, plan-specific checkout availability and charge disclosure."""
from typing import Literal, TypedDict

from core.config import settings
from db.models import PricePlan
from payments import tribute


class CheckoutPaymentOption(TypedDict):
    provider: Literal["tbank", "crypto", "tribute", "lava"]
    amount: float | None
    currency: Literal["RUB", "USDT", "USD"]


def crypto_amount_usdt(price_rub: float) -> float:
    """The existing CryptoBot checkout conversion, shared with price disclosure."""
    return round(float(price_rub) / 90, 2)


def payment_options_for_plan(plan: PricePlan) -> list[CheckoutPaymentOption]:
    """Only advertise providers capable of selling this specific active plan."""
    if not bool(getattr(plan, "is_active", True)):
        return []
    options: list[CheckoutPaymentOption] = []
    if settings.TBANK_TERMINAL_KEY and settings.TBANK_PASSWORD:
        options.append({"provider": "tbank", "amount": float(plan.price_rub), "currency": "RUB"})
    if settings.CRYPTOBOT_TOKEN:
        options.append({"provider": "crypto", "amount": crypto_amount_usdt(plan.price_rub), "currency": "USDT"})
    if settings.TRIBUTE_API_KEY:
        product = tribute.digital_product_for_plan(plan.key)
        if product is not None and product.currency == "usd":
            options.append({"provider": "tribute", "amount": product.amount_major, "currency": "USD"})
    if settings.LAVA_API_KEY and settings.lava_offer_id_for_plan(plan.key):
        # create_invoice uses the provider's offer price, not the DB's RUB price.
        options.append({"provider": "lava", "amount": None, "currency": "RUB"})
    return options
