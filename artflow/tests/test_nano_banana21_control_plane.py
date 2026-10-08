from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from api import image_service, miniapp_routes, neironych_image_adapter
from api.image_service import ImageModel
from api.web import admin as web_admin
from bot.handlers import admin as bot_admin
from core import provider_routing
from db.models import GenerationStatus, GenerationType, ProviderRoutingAudit


@pytest.mark.asyncio
async def test_route_uses_environment_until_first_admin_edit(monkeypatch):
    session = SimpleNamespace(get=AsyncMock(return_value=None))
    monkeypatch.setattr(provider_routing.settings, "NANO_BANANA_21_PRIMARY_PROVIDER", "neironych")
    route = await provider_routing.get_nano21_route(session)
    assert route.primary_provider == "neironych"
    assert route.source == "environment"
    session.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_db_primary_overrides_bootstrap_environment(monkeypatch):
    monkeypatch.setattr(provider_routing.settings, "NANO_BANANA_21_PRIMARY_PROVIDER", "neironych")
    db_route = SimpleNamespace(primary_provider="nexus", updated_by_admin_tg_id=42)
    session = SimpleNamespace(get=AsyncMock(return_value=db_route))
    route = await provider_routing.get_nano21_route(session)
    assert route.primary_provider == "nexus"
    assert route.source == "database"
    assert route.updated_by_admin_tg_id == 42


@pytest.mark.asyncio
async def test_admin_route_update_writes_audit_and_commits_atomically():
    row = SimpleNamespace(primary_provider="neironych", updated_by_admin_tg_id=None)
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[None, SimpleNamespace(scalar_one=lambda: row)]),
        add=MagicMock(),
        commit=AsyncMock(),
    )
    updated = await provider_routing.set_nano21_route(
        session, "nexus", admin_tg_id=987, source="telegram"
    )
    assert updated.primary_provider == "nexus"
    assert row.updated_by_admin_tg_id == 987
    audit = session.add.call_args.args[0]
    assert isinstance(audit, ProviderRoutingAudit)
    assert (audit.previous_provider, audit.new_provider) == ("neironych", "nexus")
    assert audit.changed_by_admin_tg_id == 987
    assert audit.source == "telegram"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_route_noop_does_not_fabricate_audit():
    row = SimpleNamespace(primary_provider="nexus", updated_by_admin_tg_id=888)
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[None, SimpleNamespace(scalar_one=lambda: row)]),
        add=MagicMock(),
        commit=AsyncMock(),
    )
    await provider_routing.set_nano21_route(session, "nexus", admin_tg_id=987, source="web")
    session.add.assert_not_called()
    assert row.updated_by_admin_tg_id == 888


@pytest.mark.asyncio
async def test_web_admin_provider_routes_are_admin_only(monkeypatch):
    monkeypatch.setattr(web_admin.settings, "ADMIN_IDS", [42])
    session = object()
    request = web_admin.Nano21ProviderRoutingUpdate(primary_provider="nexus")
    assert (await web_admin.admin_get_nano21_provider(session=session, user=None)).status_code == 401
    assert (await web_admin.admin_get_nano21_provider(session=session, user=SimpleNamespace(tg_id=7))).status_code == 403
    assert (await web_admin.admin_set_nano21_provider(body=request, session=session, user=None)).status_code == 401
    assert (await web_admin.admin_set_nano21_provider(body=request, session=session, user=SimpleNamespace(tg_id=7))).status_code == 403
    with pytest.raises(ValidationError):
        web_admin.Nano21ProviderRoutingUpdate(primary_provider="kie")


@pytest.mark.asyncio
async def test_web_admin_switch_persists_audit_actor(monkeypatch):
    monkeypatch.setattr(web_admin.settings, "ADMIN_IDS", [42])
    setting = provider_routing.ProviderRoute("nano-banana-2.1", "nexus", "database", 42)
    write = AsyncMock(return_value=setting)
    monkeypatch.setattr(web_admin, "set_nano21_route", write)
    response = await web_admin.admin_set_nano21_provider(
        body=web_admin.Nano21ProviderRoutingUpdate(primary_provider="nexus"),
        session=object(), user=SimpleNamespace(tg_id=42),
    )
    assert response["ok"] is True
    assert response["data"]["primary_provider"] == "nexus"
    write.assert_awaited_once_with(
        ANY,
        "nexus", admin_tg_id=42, source="web",
    )


def test_telegram_admin_control_exposes_both_providers():
    menu = bot_admin.admin_menu_kb()
    callbacks = {button.callback_data for row in menu.inline_keyboard for button in row}
    assert "adm:nano21_route" in callbacks
    opts = bot_admin._nano21_provider_kb("neironych")
    labels = [button.text for row in opts.inline_keyboard for button in row]
    assert any("✅ Нейроныч" in text for text in labels)
    assert any("Nexus" in text for text in labels)


@pytest.mark.asyncio
async def test_nano21_direct_primary_is_configurable_without_redeploy(monkeypatch):
    fallback = AsyncMock(return_value="nexus:task")
    primary = AsyncMock(side_effect=AssertionError("config switched to Nexus"))
    monkeypatch.setattr(image_service.neironych_image_adapter, "generate_nano_banana21_image", primary)
    monkeypatch.setattr(image_service.nexus_image_adapter, "create_nexus_image_task", fallback)
    result = await image_service.generate_image(
        ImageModel.NANO_BANANA_21, "A photo",
        aspect_ratio="1:1", quality="1K", primary_provider="nexus",
    )
    assert result.provider == "nexus"
    primary.assert_not_awaited()
    fallback.assert_awaited_once()


@pytest.mark.asyncio
async def test_neironych_completed_with_url_finishes_once_and_delivers(monkeypatch):
    import uuid

    request_id = str(uuid.uuid4())
    gen = SimpleNamespace(
        id=101, user_id=2, task_id=f"neironych-image:{request_id}",
        image_session_id=30, status=GenerationStatus.processing,
        gen_type=GenerationType.image, model="nano-banana-2.1",
        created_at=None,
    )
    result_url = "https://cdn.example.test/generated.png"
    monkeypatch.setattr(
        neironych_image_adapter, "fetch_nano_banana21_status",
        AsyncMock(return_value={"status": "completed", "result_url": result_url}),
    )
    completed = SimpleNamespace(id=101, user_id=2, task_id=gen.task_id)
    finish = AsyncMock(return_value=completed)
    deliver = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "finish_generation", finish)
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id", AsyncMock(return_value=completed))
    monkeypatch.setattr(miniapp_routes.repo, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(tg_id=555)))
    monkeypatch.setattr(miniapp_routes.repo, "update_image_session_last_result", AsyncMock())
    monkeypatch.setattr(miniapp_routes, "_notify_direct_image_result_in_bot", deliver)
    await miniapp_routes._reconcile_neironych_image_generation(object(), gen, request_id)
    finish.assert_awaited_once()
    deliver.assert_awaited_once()
    finish.return_value = None
    deliver.reset_mock()
    await miniapp_routes._reconcile_neironych_image_generation(object(), gen, request_id)
    deliver.assert_not_awaited()


@pytest.mark.asyncio
async def test_neironych_confirmed_failed_refunds_once(monkeypatch):
    import uuid

    request_id = str(uuid.uuid4())
    gen = SimpleNamespace(id=202, status=GenerationStatus.processing)
    monkeypatch.setattr(
        neironych_image_adapter, "fetch_nano_banana21_status",
        AsyncMock(return_value={"status": "failed", "result_url": None}),
    )
    fail = AsyncMock(return_value=(True, 1.0))
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", fail)
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    await miniapp_routes._reconcile_neironych_image_generation(object(), gen, request_id)
    fail.assert_awaited_once()


@pytest.mark.asyncio
async def test_neironych_completed_without_file_requires_manual_resolution(monkeypatch):
    import uuid

    request_id = str(uuid.uuid4())
    gen = SimpleNamespace(id=203, status=GenerationStatus.processing)
    monkeypatch.setattr(
        neironych_image_adapter, "fetch_nano_banana21_status",
        AsyncMock(return_value={"status": "completed", "result_url": None}),
    )
    fail = AsyncMock()
    finish = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", fail)
    monkeypatch.setattr(miniapp_routes.repo, "finish_generation", finish)
    assert await miniapp_routes._reconcile_neironych_image_generation(object(), gen, request_id) is gen
    fail.assert_not_awaited()
    finish.assert_not_awaited()
