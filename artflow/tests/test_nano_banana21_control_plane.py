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
    monkeypatch.setattr(
        neironych_image_adapter,
        "mirror_verified_nano_banana21_result",
        AsyncMock(return_value=result_url),
    )
    completed = SimpleNamespace(
        id=101, user_id=2, task_id=gen.task_id,
        result_url=result_url, result_urls=None,
    )
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


@pytest.mark.asyncio
async def test_reconciled_image_is_verified_and_uses_durable_url_everywhere(monkeypatch):
    import uuid

    request_id = str(uuid.uuid4())
    temporary_url = "https://cdn.example.test/temporary.png"
    durable_url = "https://apix.example.test/static/generated/verified.png"
    gen = SimpleNamespace(
        id=301, user_id=2, task_id=f"neironych-image:{request_id}",
        image_session_id=30, status=GenerationStatus.processing,
        gen_type=GenerationType.image, model="nano-banana-2.1", created_at=None,
    )
    monkeypatch.setattr(
        neironych_image_adapter,
        "fetch_nano_banana21_status",
        AsyncMock(return_value={"status": "completed", "result_url": temporary_url}),
    )
    verify = AsyncMock(return_value=durable_url)
    monkeypatch.setattr(
        neironych_image_adapter,
        "mirror_verified_nano_banana21_result",
        verify,
        raising=False,
    )
    completed = SimpleNamespace(
        id=301, user_id=2, task_id=gen.task_id,
        result_url=durable_url, result_urls=None,
    )
    finish = AsyncMock(return_value=completed)
    update_session = AsyncMock()
    deliver = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "finish_generation", finish)
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id", AsyncMock(return_value=completed))
    monkeypatch.setattr(miniapp_routes.repo, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(tg_id=555)))
    monkeypatch.setattr(miniapp_routes.repo, "update_image_session_last_result", update_session)
    monkeypatch.setattr(miniapp_routes, "_notify_direct_image_result_in_bot", deliver)

    session = object()
    await miniapp_routes._reconcile_neironych_image_generation(session, gen, request_id)

    verify.assert_awaited_once_with(temporary_url)
    finish.assert_awaited_once_with(
        session, 301, durable_url, result_urls=[durable_url]
    )
    update_session.assert_awaited_once_with(session, 30, durable_url, 301)
    assert deliver.await_args.kwargs["result_urls"] == [durable_url]


@pytest.mark.asyncio
async def test_reconciled_invalid_image_never_finishes(monkeypatch):
    import uuid

    request_id = str(uuid.uuid4())
    gen = SimpleNamespace(
        id=302, user_id=2, task_id=f"neironych-image:{request_id}",
        image_session_id=None, status=GenerationStatus.processing,
        gen_type=GenerationType.image, model="nano-banana-2.1", created_at=None,
    )
    monkeypatch.setattr(
        neironych_image_adapter,
        "fetch_nano_banana21_status",
        AsyncMock(return_value={
            "status": "completed",
            "result_url": "https://cdn.example.test/truncated.png",
        }),
    )
    monkeypatch.setattr(
        neironych_image_adapter,
        "mirror_verified_nano_banana21_result",
        AsyncMock(side_effect=ValueError("invalid image")),
        raising=False,
    )
    finish = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "finish_generation", finish)
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id", AsyncMock(return_value=gen))

    result = await miniapp_routes._reconcile_neironych_image_generation(
        object(), gen, request_id
    )

    assert result is gen
    finish.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_rotates_forward_and_honors_stop_between_rows(monkeypatch):
    import asyncio

    from core import neironych_image_reconcile_scheduler as scheduler

    first = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    second = [SimpleNamespace(id=3), SimpleNamespace(id=4)]
    execute = AsyncMock(side_effect=[
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: first)),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: second)),
    ])
    session = SimpleNamespace(execute=execute, rollback=AsyncMock())

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    stop = asyncio.Event()
    seen = []

    async def reconcile(_session, generation):
        seen.append(generation.id)
        if generation.id == 3:
            stop.set()

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(miniapp_routes, "_reconcile_generation_status", reconcile)
    monkeypatch.setattr(scheduler.settings, "NEIRONYCH_IMAGE_RECONCILE_BATCH_SIZE", 2)
    monkeypatch.setattr(scheduler, "_last_reconciled_id", 0, raising=False)

    assert await scheduler.reconcile_neironych_images_once() == 2
    assert await scheduler.reconcile_neironych_images_once(stop) == 1
    assert seen == [1, 2, 3]
    second_statement = str(execute.await_args_list[1].args[0])
    assert "generations.id >" in second_statement
