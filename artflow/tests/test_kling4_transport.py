import httpx
import pytest

from api import kieai_client as client
from api.kling4_contract import REFERENCE_MODEL


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [429, 433, 505])
async def test_documented_rejection_never_holds_an_unknown_charge(monkeypatch, code):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"code": code, "msg": "rejected"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="https://api.kie.ai"
    ) as transport:
        monkeypatch.setattr(client, "get_client", lambda: transport)
        with pytest.raises(client.KieDefiniteRejection):
            await client.create_task({"model": REFERENCE_MODEL, "input": {}})
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body", [{"data": {"taskId": "maybe"}}, {"code": 200, "data": {}}, {"code": 500}]
)
async def test_missing_code_identity_or_uncertain_failure_is_never_retried(monkeypatch, body):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="https://api.kie.ai"
    ) as transport:
        monkeypatch.setattr(client, "get_client", lambda: transport)
        with pytest.raises(client.KieSubmissionOutcomeUnknown):
            await client.create_task({"model": REFERENCE_MODEL, "input": {}})
    assert len(calls) == 1
