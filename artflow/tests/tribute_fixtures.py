"""Explicit synthetic catalog rows for checkout tests; never imported at runtime."""
from db.models import TributeProduct
from payments.tribute import TributeDigitalProduct

PRODUCTS = {
    "credits_15": (152362, "DDs", 200), "credits_25": (152363, "DDt", 300),
    "credits_50": (152364, "DDu", 590), "credits_100_999": (152365, "DDv", 1200),
    "credits_200": (152366, "DDw", 2400), "credits_500": (152367, "DDx", 5800),
}


def with_tribute_offer(plan):
    if plan.key not in PRODUCTS:
        return plan
    product_id, slug, minor = PRODUCTS[plan.key]
    if not hasattr(plan, "credits"):
        plan.credits = 15
    plan.tribute_products = [TributeProduct(product_id=product_id, plan_key=plan.key,
        payment_url="https://web.tribute.tg/p/" + slug, currency="usd", amount_minor=minor,
        credits=plan.credits, amount_rub=plan.price_rub, revision=1, enabled=True)]
    return plan


def catalog_offer(key="credits_15", *, credits=15, amount_rub=150):
    product_id, slug, minor = PRODUCTS[key]
    return TributeDigitalProduct(key, product_id, "https://web.tribute.tg/p/" + slug,
        "usd", minor, credits, amount_rub, 1)
