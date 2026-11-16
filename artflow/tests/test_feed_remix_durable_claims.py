"""Feed-remix exact paid admission: no duplicate charge after an ambiguous POST."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api import miniapp_routes as routes
from db import feed_remix_claims as claims
from db.models import FeedRemixClaim


def body(*, key: str | None = "ab" * 16, model: str = "nano-banana-2"):
    return routes.FeedRemixRequest(
        model=model, change_request="Make the sky blue",
        reference_urls=["https://example.invalid/reference.jpg"],
        idempotency_key=key,
    )


def test_fingerprint_binds_source_surface_and_payload_but_not_the_key():
    first = routes._feed_remix_request_hash(18, body(key="ab" * 16), surface="miniapp")
    assert len(first) == 64
    assert first == routes._feed_remix_request_hash(18, body(key="cd" * 16), surface="miniapp")
    assert first != routes._feed_remix_request_hash(19, body(), surface="miniapp")
    assert first != routes._feed_remix_request_hash(18, body(model="nano-banana-2.1"), surface="miniapp")
    assert first != routes._feed_remix_request_hash(18, body(), surface="web")


@pytest.mark.parametrize("key", ["short", "invalid!", "a" * 129])
def test_untrusted_key_cannot_bypass_input_validation(key):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        body(key=key)


@pytest.mark.asyncio
async def test_duplicate_key_returns_exact_owned_generation_without_new_submission(monkeypatch):
    user = SimpleNamespace(id=17)
    previous = SimpleNamespace(id=991, user_id=17)
    session = AsyncMock()
    seen = AsyncMock(return_value=previous)
    monkeypatch.setattr(routes.repo, "get_generation_by_id", seen)
    monkeypatch.setattr(routes, "_gen_out", lambda gen: ("GENERATION", gen.id))
    claim = SimpleNamespace(
        source_generation_id=18,
        request_hash="f" * 64,
        generation_id=991,
    )
    result = await routes._existing_feed_remix_claim_response(
        session, user, claim, source_id=18, request_hash="f" * 64,
    )
    assert result == ("GENERATION", 991)
    seen.assert_awaited_once_with(session, 991)


@pytest.mark.asyncio
async def test_conflicting_or_unlinked_claim_blocks_paid_replay(monkeypatch):
    session = AsyncMock()
    user = SimpleNamespace(id=17)
    read_generation = AsyncMock()
    monkeypatch.setattr(routes.repo, "get_generation_by_id", read_generation)
    for source_id, request_hash, claim in (
        (19, "f" * 64, SimpleNamespace(source_generation_id=18, request_hash="f" * 64, generation_id=991)),
        (18, "a" * 64, SimpleNamespace(source_generation_id=18, request_hash="f" * 64, generation_id=991)),
        (18, "f" * 64, SimpleNamespace(source_generation_id=18, request_hash="f" * 64, generation_id=None)),
    ):
        with pytest.raises(HTTPException) as exc:
            await routes._existing_feed_remix_claim_response(
                session, user, claim, source_id=source_id, request_hash=request_hash,
            )
        assert exc.value.status_code == 409
    read_generation.assert_not_awaited()


@pytest.mark.asyncio
async def test_exact_get_is_user_scoped_and_never_initiates_generation(monkeypatch):
    session = AsyncMock()
    owner = SimpleNamespace(id=17)
    key = "ab" * 16
    get_claim = AsyncMock(return_value=SimpleNamespace(generation_id=991))
    get_gen = AsyncMock(return_value=SimpleNamespace(id=991, user_id=17))
    monkeypatch.setattr(routes.feed_remix_claims, "get_claim", get_claim)
    monkeypatch.setattr(routes.repo, "get_generation_by_id", get_gen)
    monkeypatch.setattr(routes, "_gen_out", lambda gen: SimpleNamespace(
        model_dump=lambda **_: {"id": gen.id, "status": "processing"},
    ))
    response = await routes.feed_remix_claim_status(key, session=session, user=owner)
    assert response == {"state": "complete", "task": {"id": 991, "status": "processing"}}
    get_claim.assert_awaited_once_with(session, user_id=17, request_key=key)
    get_gen.assert_awaited_once_with(session, 991)
    get_gen.return_value.user_id = 99
    assert await routes.feed_remix_claim_status(key, session=session, user=owner) == {
        "state": "unavailable", "task": None,
    }
    get_claim.return_value.generation_id = None
    assert await routes.feed_remix_claim_status(key, session=session, user=owner) == {
        "state": "processing", "task": None,
    }
    get_claim.return_value = None
    assert await routes.feed_remix_claim_status(key, session=session, user=owner) == {
        "state": "unavailable", "task": None,
    }


@pytest.mark.asyncio
async def test_claim_binding_is_a_guarded_compare_and_swap():
    session = AsyncMock()
    session.execute.return_value = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = 5
    assert await claims.link_generation(
        session, user_id=17, request_key="ab" * 16, generation_id=991,
    )
    stmt = str(session.execute.await_args.args[0])
    assert "feed_remix_claims.generation_id IS NULL" in stmt
    assert "feed_remix_claims.user_id" in stmt
    assert "feed_remix_claims.request_key" in stmt
    assert "RETURNING feed_remix_claims.id" in stmt
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_guard_only_applies_to_unlinked_precharge_claim():
    session = AsyncMock()
    await claims.release_precharge_claim(
        session, user_id=17, request_key="ab" * 16, request_hash="f" * 64,
    )
    stmt = str(session.execute.await_args.args[0])
    assert "feed_remix_claims.generation_id IS NULL" in stmt
    assert "feed_remix_claims.request_hash" in stmt
    session.commit.assert_awaited_once()


def test_webview_persists_exact_key_and_does_not_allow_keyed_manual_override():
    src = (
        Path(__file__).parents[1] / "webapp/src/features/feed-remix-runner.tsx"
    ).read_text()
    assert "idempotency_key: requestKey" in src
    assert "window.crypto.getRandomValues(bytes)" in src
    assert "writeLaunchMarker(scope, true, requestKey)" in src
    assert "/feed/remix-claim/" in src
    assert "!readLaunchRequestKey(activeScope.current)" in src
    assert '"feed_remix_precharge_denied", "feed_remix_preadmission_price_changed"' in src
    assert 'runError.code || ""' in src
    assert "runError.status !== 409" not in src


def test_paid_admission_and_binding_happen_before_provider_call():
    src = Path(routes.__file__).read_text()
    start = src.index('async def remix_feed_post(')
    end = src.index('@router.get("/feed/{gen_id}/link")', start)
    region = src[start:end]
    assert region.count("await reserve_before_charge()") == 2
    assert region.count("await link_before_provider_submit(gen.id)") == 2
    assert region.index("await reserve_before_charge()") < region.index("charge_image_generation(")
    assert region.index("await link_before_provider_submit(gen.id)") < region.index("midjourney_service.imagine(")
    assert region.rindex("await link_before_provider_submit(gen.id)") < region.index("result = await", region.index("await link_before_provider_submit(gen.id)", region.index("await link_before_provider_submit(gen.id)") + 1))


@pytest.mark.asyncio
async def test_sqlite_unique_user_key_and_one_time_generation_binding():
    """Real SQL unique index and CAS, no production database or paid provider."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(FeedRemixClaim.__table__.create)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            first, created = await claims.reserve_claim(
                session, user_id=17, request_key="ab" * 16,
                request_hash="f" * 64, source_generation_id=99,
            )
            assert created is True
            second, created_again = await claims.reserve_claim(
                session, user_id=17, request_key="ab" * 16,
                request_hash="f" * 64, source_generation_id=99,
            )
            assert created_again is False
            assert first.id == second.id
            assert await claims.link_generation(
                session, user_id=17, request_key="ab" * 16, generation_id=1001,
            )
            assert not await claims.link_generation(
                session, user_id=17, request_key="ab" * 16, generation_id=1002,
            )
            await claims.release_precharge_claim(
                session, user_id=17, request_key="ab" * 16, request_hash="f" * 64,
            )
            linked = await claims.get_claim(
                session, user_id=17, request_key="ab" * 16,
            )
            assert linked is not None
            assert linked.generation_id == 1001
            assert linked.status == "linked"
            other, other_created = await claims.reserve_claim(
                session, user_id=18, request_key="ab" * 16,
                request_hash="z" * 64, source_generation_id=100,
            )
            assert other_created and other.user_id == 18
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_precharge_reject_releases_only_original_unlinked_request():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(FeedRemixClaim.__table__.create)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            await claims.reserve_claim(
                session, user_id=17, request_key="ac" * 16,
                request_hash="f" * 64, source_generation_id=99,
            )
            await claims.release_precharge_claim(
                session, user_id=17, request_key="ac" * 16,
                request_hash="0" * 64,
            )
            assert await claims.get_claim(session, user_id=17, request_key="ac" * 16)
            await claims.release_precharge_claim(
                session, user_id=17, request_key="ac" * 16,
                request_hash="f" * 64,
            )
            assert await claims.get_claim(
                session, user_id=17, request_key="ac" * 16,
            ) is None
    finally:
        await engine.dispose()
