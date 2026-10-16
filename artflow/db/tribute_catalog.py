"""Validated, optimistic-versioned Tribute product offers and immutable audit."""
from __future__ import annotations

import math
import re
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PricePlan, TributeProduct, TributeProductAudit


class CatalogConflict(ValueError):
    pass


def product_payload(row: TributeProduct) -> dict:
    return {key: getattr(row, key) for key in (
        "product_id", "plan_key", "payment_url", "currency", "amount_minor",
        "credits", "amount_rub", "enabled", "revision",
    )}


def validate_product(product_id: int, payment_url: str, currency: str, amount_minor: int) -> None:
    if type(product_id) is not int or not 0 < product_id < 2**63:
        raise ValueError("Product ID must be a positive integer")
    if type(amount_minor) is not int or not 0 < amount_minor < 2**63:
        raise ValueError("Amount must be positive integer minor units")
    if currency != "usd":
        raise ValueError("This checkout supports USD digital products")
    url = urlsplit(payment_url)
    if (url.scheme != "https" or url.netloc != "web.tribute.tg"
            or not re.fullmatch(r"/p/[A-Za-z0-9]+", url.path)
            or url.query or url.fragment or len(payment_url) > 2048):
        raise ValueError("Use the canonical HTTPS Tribute digital product link")


async def list_products(session: AsyncSession) -> list[dict]:
    return [product_payload(row) for row in (await session.scalars(
        select(TributeProduct).order_by(TributeProduct.plan_key, TributeProduct.product_id)
    )).all()]


async def save_product(
    session: AsyncSession, *, product_id: int, plan_key: str, payment_url: str,
    currency: str, amount_minor: int, enabled: bool, expected_revision: int,
    admin_tg_id: int, source: str = "web",
) -> dict:
    validate_product(product_id, payment_url, currency, amount_minor)
    if not admin_tg_id or source not in {"web", "telegram"}:
        raise ValueError("An authenticated administrator is required")
    try:
        # The plan lock also serializes replacement by two new product IDs.
        plan = await session.scalar(select(PricePlan).where(PricePlan.key == plan_key).with_for_update().execution_options(populate_existing=True))
        if plan is None:
            raise ValueError("Price plan not found")
        if any(not math.isfinite(v) or v <= 0 for v in (plan.credits, plan.price_rub)):
            raise ValueError("Price plan must have finite positive economic terms")
        row = await session.scalar(select(TributeProduct).where(TributeProduct.product_id == product_id).with_for_update().execution_options(populate_existing=True))
        if (row.revision if row else 0) != expected_revision:
            raise CatalogConflict("Catalog changed; reload before saving")
        previous = product_payload(row) if row else None
        if row and (
            (row.plan_key, row.currency, row.amount_minor) != (plan_key, currency, amount_minor)
            or enabled and (row.credits, row.amount_rub) != (plan.credits, plan.price_rub)
        ):
            raise CatalogConflict("Changed economic terms require a new Tribute product ID; old purchases retain their terms")
        if enabled:
            if not plan.is_active:
                raise ValueError("Cannot enable checkout for an inactive plan")
            old_rows = (await session.scalars(select(TributeProduct).where(
                TributeProduct.plan_key == plan_key, TributeProduct.enabled.is_(True),
                TributeProduct.product_id != product_id,
            ).with_for_update().execution_options(populate_existing=True))).all()
            for old in old_rows:
                old_data = product_payload(old)
                old.enabled = False
                old.revision += 1
                session.add(TributeProductAudit(product_id=old.product_id, previous=old_data,
                    current=product_payload(old), admin_tg_id=admin_tg_id, source=source))
            await session.flush()
        if row is None:
            row = TributeProduct(product_id=product_id, plan_key=plan_key, currency=currency,
                amount_minor=amount_minor, credits=plan.credits, amount_rub=plan.price_rub,
                payment_url=payment_url, enabled=enabled, revision=1)
            session.add(row)
            await session.flush()
        else:
            row.payment_url = payment_url
            row.enabled = enabled
            row.revision += 1
        current = product_payload(row)
        session.add(TributeProductAudit(product_id=product_id, previous=previous, current=current,
            admin_tg_id=admin_tg_id, source=source))
        await session.commit()
        return current
    except Exception:
        await session.rollback()
        raise
