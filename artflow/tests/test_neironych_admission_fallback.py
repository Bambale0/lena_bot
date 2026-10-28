"""Only the verified native pre-admission error can safely use the backup.

All HTTP is synthetic. No provider job, secret, real balance or DB is used.
The upstream contract was checked at ooo@50963d35033497d5014b830bf3a1eda263d72402.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from api import photo_prompt_service, seedance_provider_routing
from api.neironych_qwen38_service import NeironychQwen38Service, Qwen38ProviderError
from api.neironych_seedance import NeironychSeedanceClient, NeironychSubmissionUnknown
from tests import test_kie_seedance_callback as kie_fixtures

kie_transaction_db = kie_fixtures.kie_transaction_db

TRACE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
CLIENT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
HEADERS = {"X-Request-Id": TRACE}
ADMISSION_BODY = {"detail": "provider_temporarily_unavailable"}


async def submit_video(response, monkeypatch):
    monkeypatch.setattr(seedance_provider_routing.settings, "SEEDANCE_PRIMARY_PROVIDER", "neironych")
    requests = []
    before = AsyncMock()
    backup = AsyncMock(return_value="kie-accepted-once")

    def handler(request):
        requests.append(request)
        return response

    async with httpx.AsyncClient(base_url="https://provider.test", transport=httpx.MockTransport(handler)) as http:
        client = NeironychSeedanceClient("synthetic-key", "https://provider.test", client=http)

        async def primary():
            return await client.create_video(
                model="seedance-2.5", payload={"prompt": "A still life", "duration": 5, "resolution": "720p"},
                idempotency_key="test-admission-503", client_request_id=CLIENT_ID, before_submit=before,
            )

        try:
            result = await seedance_provider_routing.submit_seedance(
                "bytedance/seedance-2-5", neironych=primary, kie=backup,
            )
        except NeironychSubmissionUnknown:
            backup.assert_not_awaited()
            raise
    assert len(requests) == 1
    before.assert_awaited_once()
    backup.assert_awaited_once()
    assert result == "kie-accepted-once"
    return requests


@pytest.mark.asyncio
async def test_seedance_native_capital_rejection_uses_backup_exactly_once(monkeypatch):
    requests = await submit_video(httpx.Response(503, headers=HEADERS, json=ADMISSION_BODY), monkeypatch)
    assert requests[0].headers["Idempotency-Key"] == "test-admission-503"


UNKNOWN_RESPONSES = [
    httpx.Response(503, json=ADMISSION_BODY),  # no native diagnostic UUID
    httpx.Response(503, headers={"X-Request-Id": "not-a-uuid"}, json=ADMISSION_BODY),
    httpx.Response(503, headers={"X-Request-Id": "https://secret.test/?token=hidden"}, json=ADMISSION_BODY),
    httpx.Response(503, headers=HEADERS, json={**ADMISSION_BODY, "request_id": TRACE}),
    httpx.Response(503, headers=HEADERS, json={"error": {"type": "provider_temporarily_unavailable"}, "request_id": TRACE}),
    httpx.Response(503, headers=HEADERS, json={"detail": "unclassified_provider_error"}),
    httpx.Response(503, headers=HEADERS, text="provider_temporarily_unavailable"),
    httpx.Response(503, headers={**HEADERS, "Content-Type": "text/html"}, json=ADMISSION_BODY),
    httpx.Response(503, headers=HEADERS, json=[ADMISSION_BODY]),
    httpx.Response(502, headers=HEADERS, json=ADMISSION_BODY),
    httpx.Response(504, headers=HEADERS, json=ADMISSION_BODY),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("response", UNKNOWN_RESPONSES)
async def test_unknown_seedance_5xx_never_authorizes_backup(monkeypatch, response):
    with pytest.raises(NeironychSubmissionUnknown):
        await submit_video(response, monkeypatch)


def qwen(response):
    return NeironychQwen38Service(
        api_key="synthetic-key", base_url="https://provider.test", model="qwen3.8-max",
        transport=httpx.MockTransport(lambda request: response),
    )


@pytest.mark.asyncio
async def test_qwen_native_capital_rejection_is_not_ambiguous():
    with pytest.raises(Qwen38ProviderError) as caught:
        await qwen(httpx.Response(503, headers=HEADERS, json=ADMISSION_BODY)).analyze_text(user_instruction="Hello")
    assert caught.value.ambiguous is False
    assert caught.value.kind == "admission_rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize("response", UNKNOWN_RESPONSES)
async def test_qwen_unproven_5xx_remains_ambiguous(response):
    with pytest.raises(Qwen38ProviderError) as caught:
        await qwen(response).analyze_text(user_instruction="Hello")
    assert caught.value.ambiguous is True


@pytest.mark.asyncio
async def test_shared_photo_prompt_uses_existing_configured_backup_after_capital_rejection(monkeypatch):
    service = qwen(httpx.Response(503, headers=HEADERS, json=ADMISSION_BODY))
    monkeypatch.setattr(photo_prompt_service, "NeironychQwen38Service", lambda: service)
    monkeypatch.setattr(photo_prompt_service, "get_qwen_route", AsyncMock(return_value=SimpleNamespace(
        primary_provider="neironych", backup_provider="kie",
    )))
    monkeypatch.setattr(photo_prompt_service.settings, "KIE_PHOTO_PROMPT_MODEL", "gpt-5-2")
    backup = AsyncMock(return_value=photo_prompt_service.PhotoPromptResult(
        "A sufficiently descriptive synthetic photo prompt.", "kie", "gpt-5-2",
    ))
    monkeypatch.setattr(photo_prompt_service, "_call_kie_chat", backup)
    result = await photo_prompt_service.generate_prompt_from_photo_result(b"synthetic photo", "image/png")
    assert result.provider == "kie"
    backup.assert_awaited_once()
    assert backup.await_args.args[1].startswith("data:image/png;base64,")


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["production25", "legacy25", "production20"])
@pytest.mark.parametrize("backup_outcome", ["accepted", "timeout", "journal_failure"])
async def test_seedance_fallback_journal_precedes_kie_http_and_binds_result(
    monkeypatch, kie_transaction_db, entrypoint, backup_outcome,
):
    import json

    from sqlalchemy.orm import Session

    from api import kieai_client, seedance25_adapter, video_runtime_fixes, video_service
    from api import neironych_seedance_runtime as runtime
    from api.neironych_seedance import NeironychPreSubmitFailure
    from core import seedance_reconciliation as reconciliation
    from db import repository as repo
    from db.models import Generation, GenerationStatus, User
    from tests.test_kie_seedance_callback import LocalAsyncSession

    model = "bytedance/seedance-2" if entrypoint == "production20" else "bytedance/seedance-2-5"
    image = "https://example.test/reader.jpg"
    calls = []
    monkeypatch.setattr(seedance_provider_routing.settings, "SEEDANCE_PRIMARY_PROVIDER", "neironych")
    monkeypatch.setattr(video_service, "ensure_video_reference_aspect_url", lambda url, **kw: url)
    monkeypatch.setattr(video_runtime_fixes, "ensure_video_reference_aspect_url", lambda url, **kw: url)
    monkeypatch.setattr(video_service, "_prepare_video_reference_urls", AsyncMock(side_effect=lambda urls: urls))
    monkeypatch.setattr(video_service, "_prepare_video_reference_url", AsyncMock(side_effect=lambda url: url))
    monkeypatch.setattr(video_service, "_prepare_reference_video_url", AsyncMock(side_effect=lambda url: url))

    with Session(kie_transaction_db, expire_on_commit=False) as session:
        gen = session.get(Generation, 73)
        gen.task_id, gen.input_params, gen.status, gen.model = None, "{}", GenerationStatus.pending, model
        session.commit()
        db = LocalAsyncSession(session)
        assert await repo.register_kie_video_callback(db, gen.id, surface="miniapp")
        context = reconciliation.make_submission_context(db, gen.id, model)
        if backup_outcome == "journal_failure":
            context.before_kie_submit = AsyncMock(side_effect=NeironychPreSubmitFailure(
                context.client_request_id, "synthetic-video-73",
            ))

        def primary(request):
            calls.append(("neironych", json.loads(request.content)))
            assert session.get(Generation, 73).task_id == "neironych-submit:" + context.client_request_id
            return httpx.Response(503, headers=HEADERS, json=ADMISSION_BODY)

        def backup(request):
            row = session.get(Generation, 73)
            assert row.task_id == "kie-submit:73", "KIE must be journaled before its paid POST"
            assert json.loads(row.input_params)[repo.SEEDANCE_SUBMISSION_KEY]["state"] == "definite_rejected_fallback_kie"
            calls.append(("kie", json.loads(request.content)))
            if backup_outcome == "timeout":
                raise httpx.ReadTimeout("synthetic lost KIE response", request=request)
            return httpx.Response(200, json={"code": 200, "data": {"taskId": "synthetic-kie-task"}})

        async with (
            httpx.AsyncClient(base_url="https://provider.test", transport=httpx.MockTransport(primary)) as neiro_http,
            httpx.AsyncClient(base_url="https://kie.test", transport=httpx.MockTransport(backup)) as kie_http,
        ):
            neiro = NeironychSeedanceClient("synthetic-key", "https://provider.test", client=neiro_http)
            monkeypatch.setattr(runtime, "_client", lambda: neiro)
            monkeypatch.setattr(kieai_client, "get_client", lambda: kie_http)
            kwargs = dict(
                image_url=[image], duration=5, aspect_ratio="16:9", resolution="720p",
                idempotency_key="synthetic-video-73", neironych_submission=context,
                callback_url="https://example.test/signed-callback",
            )
            async def invoke():
                if entrypoint == "production25":
                    return await video_runtime_fixes._seedance_generate(video_service, "Use my reference", (), kwargs)
                elif entrypoint == "legacy25":
                    service = SimpleNamespace(
                        VideoModel=video_service.VideoModel, VideoResult=video_service.VideoResult,
                        generate_video=AsyncMock(), _prepare_video_reference_urls=video_service._prepare_video_reference_urls,
                        kieai_client=kieai_client,
                    )
                    seedance25_adapter._install_seedance25_generate_wrapper(service)
                    return await service.generate_video(video_service.VideoModel(model), "Use my reference", **kwargs)
                else:
                    return await video_service.generate_video(video_service.VideoModel(model), "Use my reference", **kwargs)

            if backup_outcome == "journal_failure":
                with pytest.raises(NeironychSubmissionUnknown):
                    await invoke()
                assert [provider for provider, _ in calls] == ["neironych"]
                assert not context.kie_started
                assert session.get(Generation, 73).task_id.startswith("neironych-submit:")
                monkeypatch.setattr(reconciliation, "pause_neironych_route", AsyncMock())
                assert await reconciliation.handle_submission_unknown(db, 73, context)
                marker = json.loads(session.get(Generation, 73).input_params)
                assert marker[repo.SEEDANCE_SUBMISSION_KEY]["state"] == "submission_unknown"
                assert marker[reconciliation.RECONCILIATION_KEY]["required"] is True
                assert session.get(User, 42).credits == 100
                return
            if backup_outcome == "timeout":
                with pytest.raises(kieai_client.KieSubmissionOutcomeUnknown):
                    await invoke()
                assert [provider for provider, _ in calls] == ["neironych", "kie"]
                assert context.kie_started
                assert session.get(Generation, 73).task_id == "kie-submit:73"
                assert session.get(User, 42).credits == 100
                assert not await repo.begin_kie_video_submission(db, 73, context.client_request_id)
                return
            result = await invoke()
        assert [provider for provider, _ in calls] == ["neironych", "kie"]
        assert image in json.dumps(calls[1][1])
        assert calls[1][1]["model"] == model
        assert result.provider == "kieai" and context.kie_started
        assert await reconciliation.persist_submission_result(db, 73, context, result.task_id)
        assert session.get(Generation, 73).task_id == "synthetic-kie-task"
        assert session.get(User, 42).credits == 100  # provider fallback never charges a second time
        assert not await repo.begin_kie_video_submission(db, 73, context.client_request_id)




@pytest.mark.asyncio
async def test_lost_kie_journal_ack_preserves_kie_identity_for_reconciliation(kie_transaction_db):
    import json

    from sqlalchemy.orm import Session

    from core import seedance_reconciliation as reconciliation
    from db import repository as repo
    from db.models import Generation, GenerationStatus, User
    from tests.test_kie_seedance_callback import LocalAsyncSession

    with Session(kie_transaction_db, expire_on_commit=False) as session:
        row = session.get(Generation, 73)
        row.task_id, row.input_params, row.status = None, "{}", GenerationStatus.pending
        session.commit()
        db = LocalAsyncSession(session)
        assert await repo.register_kie_video_callback(db, 73, surface="miniapp")
        context = reconciliation.make_submission_context(db, 73, row.model)
        await context.before_submit("synthetic-video-73", "a" * 64)
        # Simulate COMMIT success with the acknowledgment lost before the
        # in-memory context could observe it. No provider HTTP has occurred.
        assert await repo.begin_kie_video_submission(db, 73, context.client_request_id)
        assert context.kie_started is False
        assert await reconciliation.handle_submission_unknown(db, 73, context)
        row = session.get(Generation, 73)
        assert row.task_id == "kie-submit:73"
        assert json.loads(row.input_params)[repo.KIE_VIDEO_SUBMISSION_KEY]["state"] == "submission_unknown"
        assert not await repo.begin_kie_video_submission(db, 73, context.client_request_id)
        assert session.get(User, 42).credits == 100


@pytest.mark.asyncio
async def test_wan_kie_primary_definite_rejection_transfers_journal_to_neironych(
    monkeypatch, kie_transaction_db,
):
    """The real checkout context must change ownership before the fallback POST."""
    import json

    from sqlalchemy.orm import Session

    from api import kieai_client, wan30_provider
    from api.wan30_contract import Wan30Request
    from core import seedance_reconciliation as reconciliation
    from core.wan30_routing_policy import WanRoute
    from db import repository as repo
    from db.models import Generation, GenerationStatus, User
    from tests.test_kie_seedance_callback import LocalAsyncSession

    with Session(kie_transaction_db, expire_on_commit=False) as session:
        row = session.get(Generation, 73)
        row.task_id = None
        row.input_params = "{}"
        row.status = GenerationStatus.pending
        row.model = "wan/3-0-video"
        session.commit()
        db = LocalAsyncSession(session)
        assert await repo.register_kie_video_callback(db, row.id, surface="miniapp")
        context = reconciliation.make_submission_context(db, row.id, row.model)

        monkeypatch.setattr(
            wan30_provider,
            "get_wan30_route",
            AsyncMock(return_value=WanRoute(
                row.model, "kie_neironych", "wan-3", 3, "database", 42,
            )),
        )
        monkeypatch.setattr(wan30_provider.settings, "NEIRONYCH_API_KEY", "synthetic")
        async def advertised_models(_client):
            persisted = session.get(Generation, 73)
            marker = json.loads(persisted.input_params)
            assert marker[repo.KIE_VIDEO_SUBMISSION_KEY]["state"] == (
                "definite_rejected_neironych_pending"
            )
            return ["wan-3"]

        monkeypatch.setattr(
            NeironychSeedanceClient, "list_models", advertised_models,
        )
        monkeypatch.setattr(
            kieai_client, "create_task",
            AsyncMock(side_effect=kieai_client.KieDefiniteRejection("synthetic reject")),
        )

        async def neironych_paid(**kwargs):
            await kwargs["before_submit"](
                kwargs["idempotency_key"], "c" * 64,
            )
            persisted = session.get(Generation, 73)
            marker = json.loads(persisted.input_params)
            assert persisted.task_id == "neironych-submit:" + context.client_request_id
            assert marker[repo.KIE_VIDEO_SUBMISSION_KEY]["state"] == (
                "definite_rejected_fallback_neironych"
            )
            return "neironych-fallback-73"

        monkeypatch.setattr(wan30_provider, "post_wan30_neironych", neironych_paid)
        result = await wan30_provider.submit_wan30_provider(
            Wan30Request(model=row.model, prompt="Synthetic paper boat"),
            idempotency_key="synthetic-wan-73",
            submission_context=context,
        )

        assert result.provider == "neironych"
        assert context.started is True and context.kie_started is False
        assert await reconciliation.persist_submission_result(
            db, 73, context, result.task_id,
        )
        assert session.get(Generation, 73).task_id == "neironych:neironych-fallback-73"
        assert await repo.bind_kie_video_callback(db, 73, "impossible-late-kie") is None
        assert session.get(Generation, 73).task_id == "neironych:neironych-fallback-73"
        assert session.get(User, 42).credits == 100


@pytest.mark.asyncio
async def test_crash_after_kie_rejection_resumes_only_neironych_fallback(
    monkeypatch, kie_transaction_db,
):
    """A committed KIE rejection remains resumable without replaying KIE."""
    import json
    from dataclasses import asdict

    from sqlalchemy.orm import Session

    from api import kieai_client, wan30_provider
    from api.wan30_contract import Wan30Request
    from core import neironych_video_reconcile_scheduler as scheduler
    from core import seedance_reconciliation as reconciliation
    from core.wan30_routing_policy import WanRoute
    from db import repository as repo
    from db.models import Generation, GenerationStatus
    from tests.test_kie_seedance_callback import LocalAsyncSession

    request = Wan30Request(model="wan/3-0-video", prompt="Durable paper boat")
    with Session(kie_transaction_db, expire_on_commit=False) as session:
        row = session.get(Generation, 73)
        row.task_id = None
        row.input_params = json.dumps({"wan30_request": asdict(request)})
        row.status = GenerationStatus.pending
        row.model = request.model
        session.commit()
        db = LocalAsyncSession(session)
        assert await repo.register_kie_video_callback(db, row.id, surface="miniapp")
        context = reconciliation.make_submission_context(db, row.id, row.model)

        monkeypatch.setattr(
            wan30_provider,
            "get_wan30_route",
            AsyncMock(return_value=WanRoute(
                row.model, "kie_neironych", "wan-3", 3, "database", 42,
            )),
        )
        monkeypatch.setattr(wan30_provider.settings, "NEIRONYCH_API_KEY", "synthetic")
        kie_post = AsyncMock(
            side_effect=kieai_client.KieDefiniteRejection("synthetic reject"),
        )
        monkeypatch.setattr(kieai_client, "create_task", kie_post)
        monkeypatch.setattr(
            NeironychSeedanceClient,
            "list_models",
            AsyncMock(side_effect=RuntimeError("synthetic worker exit")),
        )

        with pytest.raises(RuntimeError, match="catalog"):
            await wan30_provider.submit_wan30_provider(
                request,
                idempotency_key="apix-video-73",
                submission_context=context,
            )
        marker = json.loads(session.get(Generation, 73).input_params)
        assert marker[repo.KIE_VIDEO_SUBMISSION_KEY]["state"] == (
            "definite_rejected_neironych_pending"
        )
        kie_post.assert_awaited_once()

        monkeypatch.setattr(
            NeironychSeedanceClient,
            "list_models",
            AsyncMock(return_value=["wan-3"]),
        )

        async def resumed_paid(**kwargs):
            await kwargs["before_submit"](
                kwargs["idempotency_key"], "d" * 64,
            )
            return "neironych-resumed-73"

        monkeypatch.setattr(wan30_provider, "post_wan30_neironych", resumed_paid)
        assert await scheduler._resume_rejected_wan_kie_fallback(
            db, session.get(Generation, 73),
        )
        assert session.get(Generation, 73).task_id == (
            "neironych:neironych-resumed-73"
        )
        kie_post.assert_awaited_once()
