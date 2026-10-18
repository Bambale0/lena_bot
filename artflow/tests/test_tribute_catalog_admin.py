"""The catalog is an authenticated control-plane resource, not a source table."""
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

import main
from api.web.deps import get_web_user_or_none


@pytest.mark.asyncio
async def test_tribute_catalog_endpoint_requires_authentication():
    main.app.dependency_overrides[get_web_user_or_none] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
            response = await client.get("/api/web/admin/payments/tribute-products")
        assert response.status_code == 401
    finally:
        main.app.dependency_overrides.pop(get_web_user_or_none, None)


@pytest.mark.asyncio
async def test_tribute_catalog_endpoint_rejects_non_admin(monkeypatch):
    monkeypatch.setattr(main.settings, "ADMIN_IDS", [999])
    main.app.dependency_overrides[get_web_user_or_none] = lambda: SimpleNamespace(id=1, tg_id=123)
    try:
        async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
            response = await client.get("/api/web/admin/payments/tribute-products")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.pop(get_web_user_or_none, None)


import asyncio
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db import repository as repo
from db.models import Base, PricePlan, TributeProduct, TributeProductAudit
from db.session import get_session
from payments import tribute


@pytest_asyncio.fixture
async def catalog_db(monkeypatch):
    url = os.environ.get("APIX_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Disposable PostgreSQL is mandatory in backend CI")
    schema = "audit_catalog_" + uuid4().hex
    root = create_async_engine(url)
    async with root.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    names = {"price_plans", "tribute_products", "tribute_product_audit"}
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[t for t in Base.metadata.sorted_tables if t.name in names]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(PricePlan(key="pack", label="Pack", credits=15, price_rub=150, is_active=True))
        await session.commit()
    async def sessions():
        async with factory() as session:
            yield session
    main.app.dependency_overrides[get_session] = sessions
    main.app.dependency_overrides[get_web_user_or_none] = lambda: SimpleNamespace(id=1, tg_id=999)
    monkeypatch.setattr(main.settings, "ADMIN_IDS", [999])
    monkeypatch.setattr(main.settings, "TRIBUTE_API_KEY", "catalog-test")
    async def get_product(product_id):
        return {"id": product_id, "amount": 200, "type": "digital", "status": "approved", "currency": "usd", "starsAmountEnabled": False, "webLink": "https://web.tribute.tg/p/Test"}
    monkeypatch.setattr(tribute, "get_product", get_product)
    try:
        yield factory
    finally:
        main.app.dependency_overrides.pop(get_session, None)
        main.app.dependency_overrides.pop(get_web_user_or_none, None)
        await engine.dispose()
        async with root.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await root.dispose()


def update_body(**changes):
    return {"plan_key": "pack", "payment_url": "https://web.tribute.tg/p/Test", "currency": "usd", "amount_minor": 200, "enabled": True, "expected_revision": 0, **changes}


async def save(product_id=1001, **changes):
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        return await client.put(f"/api/web/admin/payments/tribute-products/{product_id}", json=update_body(**changes))


@pytest.mark.asyncio
async def test_admin_catalog_persists_offer_and_actor_audit(catalog_db):
    response = await save()
    assert response.status_code == 200, response.text
    assert response.json()["data"]["revision"] == 1
    async with catalog_db() as session:
        row = await session.get(TributeProduct, 1001)
        assert (row.credits, row.amount_rub, row.amount_minor) == (15, 150, 200)
        audit = (await session.scalars(select(TributeProductAudit))).one()
        assert audit.admin_tg_id == 999 and audit.previous is None
        assert audit.current["product_id"] == 1001


@pytest.mark.asyncio
async def test_catalog_offer_reaches_api_and_bot_without_cache_or_source_edit(catalog_db):
    from bot.keyboards.payment import plan_payment_methods_kb
    from payments.checkout_options import payment_options_for_plan
    assert (await save()).status_code == 200
    async with catalog_db() as session:
        plan = await repo.get_price_plan_by_key(session, "pack")
        options = payment_options_for_plan(plan)
        assert {"provider": "tribute", "amount": 2, "currency": "USD"} in options
        labels = [b.text for row in plan_payment_methods_kb(plan).inline_keyboard for b in row]
        assert "💵 USD · $2" in labels
    assert (await save(expected_revision=1, enabled=False)).status_code == 200
    async with catalog_db() as session:
        plan = await repo.get_price_plan_by_key(session, "pack")
        assert tribute.digital_product_for_plan(plan) is None
        # The paid purchase still resolves after retirement.
        assert (await tribute.digital_product_for_id(session, 1001)).amount_minor == 200


@pytest.mark.asyncio
async def test_catalog_replacement_retires_old_checkout_but_keeps_receipt_terms(catalog_db):
    assert (await save()).status_code == 200
    assert (await save(1002)).status_code == 200
    async with catalog_db() as session:
        plan = (await repo.get_active_price_plans(session))[0]
        assert tribute.digital_product_for_plan(plan).product_id == 1002
        assert (await session.get(TributeProduct, 1001)).enabled is False
        assert (await tribute.digital_product_for_id(session, 1001)).credits == 15
        assert len((await session.scalars(select(TributeProductAudit))).all()) == 3


@pytest.mark.asyncio
async def test_concurrent_catalog_edits_cannot_overwrite_each_other(catalog_db):
    assert (await save()).status_code == 200
    responses = await asyncio.gather(save(expected_revision=1, enabled=False), save(expected_revision=1, enabled=False))
    assert sorted(r.status_code for r in responses) == [200, 409]
    async with catalog_db() as session:
        assert (await session.get(TributeProduct, 1001)).revision == 2
        assert len((await session.scalars(select(TributeProductAudit))).all()) == 2


@pytest.mark.asyncio
async def test_changing_plan_does_not_rewrite_a_past_product_offer(catalog_db):
    assert (await save()).status_code == 200
    async with catalog_db() as session:
        plan = await repo.get_price_plan_by_key(session, "pack")
        plan.credits = 30
        await session.commit()
    assert (await save(expected_revision=1)).status_code == 409
    async with catalog_db() as session:
        plan = await repo.get_price_plan_by_key(session, "pack")
        assert tribute.digital_product_for_plan(plan) is None
        assert (await tribute.digital_product_for_id(session, 1001)).credits == 15
    assert (await save(1002)).status_code == 200
    async with catalog_db() as session:
        assert (await tribute.digital_product_for_id(session, 1002)).credits == 30


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"amount_minor": True}, {"amount_minor": 1.2}, {"amount_minor": 0},
    {"payment_url": "https://evil.test/p/Test"}, {"payment_url": "https://web.tribute.tg/p/Test?token=secret"},
    {"currency": "rub"},
])
async def test_invalid_catalog_inputs_never_write(catalog_db, changes):
    response = await save(**changes)
    assert response.status_code == 422
    async with catalog_db() as session:
        assert (await session.scalars(select(TributeProduct))).all() == []


@pytest.mark.asyncio
async def test_provider_price_mismatch_does_not_publish_catalog(catalog_db, monkeypatch):
    monkeypatch.setattr(tribute, "get_product", AsyncMock(return_value={"id": 1001, "amount": 999, "type": "digital", "status": "approved", "currency": "usd"}))
    response = await save()
    assert response.status_code == 503
    async with catalog_db() as session:
        assert (await session.scalars(select(TributeProduct))).all() == []


@pytest.mark.asyncio
async def test_retired_offer_can_be_disabled_after_plan_economics_changed(catalog_db):
    assert (await save()).status_code == 200
    async with catalog_db() as session:
        plan = await repo.get_price_plan_by_key(session, "pack")
        plan.credits = 99
        await session.commit()
    response = await save(expected_revision=1, enabled=False)
    assert response.status_code == 200
    async with catalog_db() as session:
        old = await session.get(TributeProduct, 1001)
        assert old.enabled is False and old.credits == 15
