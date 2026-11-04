"""An uncertain paid KIE submission stays correlated and is never refunded/replayed."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from api import image_service
from api import miniapp_routes as routes
from api import neironych_image_adapter as adapter
from core.kie_seedance_callback import verify_generation_signature
from db.models import GenerationStatus


@pytest.mark.parametrize("surface", ["web", "miniapp"])
@pytest.mark.parametrize("primary", ["neironych", "kie"])
async def test_kie_timeout_keeps_charge_and_signed_recovery_identity(monkeypatch, surface, primary):
    gen = SimpleNamespace(id=7801, task_id=None, status=GenerationStatus.pending)
    db = AsyncMock()
    refunds = AsyncMock()
    monkeypatch.setattr(routes, "_reconcile_user_active_generations", AsyncMock())
    monkeypatch.setattr(routes, "get_seedream5_route", AsyncMock(return_value=SimpleNamespace(primary_provider=primary)))
    monkeypatch.setattr(routes.repo, "resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=2)))
    monkeypatch.setattr(routes.repo, "count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr(routes.repo, "charge_image_generation", AsyncMock(return_value=SimpleNamespace(allowed=True, charged_credits=2, unlimited=False)))
    monkeypatch.setattr(routes.repo, "create_image_session", AsyncMock(return_value=SimpleNamespace(id=12)))
    monkeypatch.setattr(routes.repo, "create_generation", AsyncMock(return_value=gen))
    monkeypatch.setattr(routes.repo, "fail_generation_and_refund", refunds)
    monkeypatch.setattr(routes.repo, "add_credits", refunds)
    monkeypatch.setattr(routes, "_gen_out", lambda row: {"status": row.status.value, "task_id": row.task_id})
    async def save_task(session, gen_id, task_id, **kwargs):
        if "expected_task_id" in kwargs:
            assert gen.task_id == kwargs["expected_task_id"]
        gen.task_id = task_id
        gen.status = GenerationStatus.processing
        return True
    monkeypatch.setattr(routes.repo, "update_generation_task", save_task)
    monkeypatch.setattr(adapter, "generate_seedream5_image", AsyncMock(side_effect=adapter.NeironychImageRejected("balance", status_code=402)))
    calls = []
    def respond(request):
        import json
        body = json.loads(request.content)
        query = parse_qs(urlparse(body["callBackUrl"]).query)
        assert query["apix_generation_id"] == ["7801"]
        assert verify_generation_signature(7801, query["apix_generation_sig"][0])
        assert gen.task_id.endswith(adapter.encode_kie_handoff_id(adapter.client_request_id_for_generation(7801)))
        calls.append(request)
        raise httpx.ReadTimeout("accepted but reply lost", request=request)
    async with httpx.AsyncClient(base_url="https://kie.test", transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(image_service.kieai_client, "get_client", lambda: client)
        result = await routes.create_image_generation(
            routes.ImageGenRequest(model="seedream/5-pro-text-to-image", prompt="A cup", quality="basic"),
            session=db, user=SimpleNamespace(id=42, credits=100), surface=surface,
        )
    assert result["status"] == "processing"
    assert gen.task_id.startswith("web:kie-submit:" if surface == "web" else "kie-submit:")
    assert len(calls) == 1
    refunds.assert_not_awaited()
