from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_database_route_wins_over_bootstrap_and_is_audited():
    from core.wan30_routing_policy import get_wan30_route, set_wan30_route
    row = SimpleNamespace(model_key="wan/3-0-video", policy="kie_only", neironych_model_id="wan-3", revision=3, updated_by_admin_tg_id=42)
    session = SimpleNamespace(get=AsyncMock(return_value=row), execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: row)), add=MagicMock(), commit=AsyncMock())
    route = await get_wan30_route("wan/3-0-video", session)
    assert (route.policy, route.source, route.revision) == ("kie_only", "database", 3)
    saved = await set_wan30_route(session, "wan/3-0-video", policy="neironych_kie", neironych_model_id="wan-3", expected_revision=3, admin_tg_id=42, source="web")
    assert (saved.policy, saved.revision) == ("neironych_kie", 4)
    audit = session.add.call_args.args[0]
    assert audit.previous_policy == "kie_only"
    assert audit.new_policy == "neironych_kie"
    assert audit.changed_by_admin_tg_id == 42
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_stale_admin_update_cannot_overwrite_newer_route():
    from core.wan30_routing_policy import WanRouteConflict, set_wan30_route
    row = SimpleNamespace(policy="kie_only", neironych_model_id="wan-3", revision=4, updated_by_admin_tg_id=42)
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: row)), add=MagicMock(), commit=AsyncMock())
    with pytest.raises(WanRouteConflict):
        await set_wan30_route(session, "wan/3-0-video", policy="neironych_kie", neironych_model_id="wan-3", expected_revision=3, admin_tg_id=42, source="web")
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("actor, code", [(None, 401), (SimpleNamespace(tg_id=7), 403)])
async def test_admin_route_authorization_precedes_read_or_write(monkeypatch, actor, code):
    from api.web import admin
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", [42])
    getter, setter = AsyncMock(), AsyncMock()
    monkeypatch.setattr(admin, "get_wan30_route", getter)
    monkeypatch.setattr(admin, "set_wan30_route", setter)
    body = admin.WanRoutingUpdate(policy="neironych_kie", neironych_model_id="wan-3", expected_revision=1)
    assert (await admin.admin_get_wan_route("standard", session=object(), user=actor)).status_code == code
    assert (await admin.admin_set_wan_route("standard", body, session=object(), user=actor)).status_code == code
    getter.assert_not_awaited()
    setter.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_rejects_unadvertised_mapping_without_writing(monkeypatch):
    from api.neironych_seedance import NeironychSeedanceClient
    from api.web import admin
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", [42])
    monkeypatch.setattr(admin.settings, "NEIRONYCH_API_KEY", "test")
    monkeypatch.setattr(NeironychSeedanceClient, "list_models", AsyncMock(return_value=["wan-3"]))
    setter = AsyncMock()
    monkeypatch.setattr(admin, "set_wan30_route", setter)
    result = await admin.admin_set_wan_route("standard", admin.WanRoutingUpdate(policy="neironych_kie", neironych_model_id="unavailable", expected_revision=1), session=object(), user=SimpleNamespace(tg_id=42))
    assert result.status_code == 422
    setter.assert_not_awaited()


@pytest.mark.asyncio
async def test_migration_seed_runtime_change_audit_and_revision_with_real_database(tmp_path):
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from core.wan30_routing_policy import WanRouteConflict, get_wan30_route, set_wan30_route
    from db.models import WanRoutingAudit

    path = Path(__file__).resolve().parents[1] / "db/migrations/versions/048_wan_routing.py"
    spec = importlib.util.spec_from_file_location("wan_migration_test", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "wan-routing.db"))
    def upgrade(connection):
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(upgrade)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            for model, expected in [("wan/3-0-video", "wan-3"), ("wan/3-0-video-prime", "wan-3-prime")]:
                route = await get_wan30_route(model, db)
                assert (route.policy, route.neironych_model_id, route.revision, route.source) == ("neironych_kie", expected, 1, "database")
            saved = await set_wan30_route(db, "wan/3-0-video", policy="kie_only", neironych_model_id="wan-3", expected_revision=1, admin_tg_id=42, source="web")
            assert saved.revision == 2
        async with sessions() as db:
            route = await get_wan30_route("wan/3-0-video", db)
            assert route.policy == "kie_only"
            audits = (await db.execute(sa.select(WanRoutingAudit))).scalars().all()
            assert len(audits) == 1
            assert (audits[0].previous_policy, audits[0].new_policy, audits[0].revision) == ("neironych_kie", "kie_only", 2)
            with pytest.raises(WanRouteConflict):
                await set_wan30_route(db, "wan/3-0-video", policy="neironych_only", neironych_model_id="wan-3", expected_revision=1, admin_tg_id=42, source="web")
            await db.rollback()
            assert (await get_wan30_route("wan/3-0-video", db)).policy == "kie_only"
    finally:
        await engine.dispose()


@pytest.mark.parametrize("model, native", [
    ("wan/3-0-video", "seedance-2.5"),
    ("wan/3-0-video", "wan-2.6"),
    ("wan/3-0-video", "wan-30"),
    ("wan/3-0-video-prime", "wan-3"),
    ("wan/3-0-video", "wan-3-prime"),
])
def test_admin_mapping_cannot_substitute_another_model_family_or_variant(model, native):
    from core.wan30_routing_policy import validate_route
    with pytest.raises(ValueError):
        validate_route(model, "neironych_kie", native)


def test_admin_accepts_kie_primary_with_neironych_fallback_policy():
    from api.web.admin import WanRoutingUpdate
    from core.wan30_routing_policy import validate_route

    validate_route("wan/3-0-video", "kie_neironych", "wan-3")
    body = WanRoutingUpdate(
        policy="kie_neironych",
        neironych_model_id="wan-3",
        expected_revision=2,
    )

    assert body.policy == "kie_neironych"


@pytest.mark.asyncio
async def test_admin_can_switch_to_kie_without_primary_key_or_catalog(monkeypatch):
    from api.neironych_seedance import NeironychSeedanceClient
    from api.web import admin
    from core.wan30_routing_policy import WanRoute
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", [42])
    monkeypatch.setattr(admin.settings, "NEIRONYCH_API_KEY", "")
    catalog = AsyncMock(side_effect=AssertionError("KIE-only must not require primary"))
    monkeypatch.setattr(NeironychSeedanceClient, "list_models", catalog)
    setter = AsyncMock(return_value=WanRoute("wan/3-0-video", "kie_only", "wan-3", 2, "database", 42))
    monkeypatch.setattr(admin, "set_wan30_route", setter)
    result = await admin.admin_set_wan_route("standard", admin.WanRoutingUpdate(policy="kie_only", neironych_model_id="wan-3", expected_revision=1), session=object(), user=SimpleNamespace(tg_id=42))
    assert result["data"]["policy"] == "kie_only"
    assert setter.await_args.kwargs["expected_revision"] == 1
    assert setter.await_args.kwargs["admin_tg_id"] == 42
    assert setter.await_args.kwargs["source"] == "web"
    catalog.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("prime_mapping", ["", "real-wan", "wan-2.6", "wan-3", "wan-30-prime"])
async def test_migration_preserves_explicitly_disabled_primary_mapping(tmp_path, monkeypatch, prime_mapping):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from core.config import settings
    from core.wan30_routing_policy import get_wan30_route

    monkeypatch.setattr(settings, "WAN30_NEIRONYCH_MODEL_ID", "wan-3-approved")
    monkeypatch.setattr(settings, "WAN30_PRIME_NEIRONYCH_MODEL_ID", prime_mapping)
    path = Path(__file__).resolve().parents[1] / "db/migrations/versions/048_wan_routing.py"
    spec = importlib.util.spec_from_file_location("wan_disabled_migration_test", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "disabled.db"))
    def upgrade(connection):
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(upgrade)
        async with async_sessionmaker(engine)() as db:
            standard = await get_wan30_route("wan/3-0-video", db)
            prime = await get_wan30_route("wan/3-0-video-prime", db)
            assert standard.neironych_model_id == "wan-3-approved"
            assert standard.policy == "neironych_kie"
            assert prime.policy == "kie_only"
    finally:
        await engine.dispose()
