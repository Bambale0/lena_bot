"""No real paid WAN submissions. MockTransport verifies the exact HTTP contract."""
import httpx
import pytest

from api.neironych_seedance import (
    NeironychSeedanceError,
    NeironychSubmissionUnknown,
)
from api.wan30_neironych_transport import post_wan30_neironych


@pytest.mark.asyncio
async def test_neironych_wan_http_single_post_and_durable_pre_submit():
    captured = []
    durable = []

    async def handler(req):
        captured.append(req)
        return httpx.Response(202, json={
            "request_id": "nwan_789",
            "client_request_id": "d4496f2e-37d8-4b87-bba2-330374892b49",
        })

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.test",
    ) as client:
        result = await post_wan30_neironych(
            client=client,
            api_key="placeholder-key",
            payload={"model":"wan-real-id","mode":"text","prompt":"hi"},
            idempotency_key="apix-wan30-789",
            client_request_id="d4496f2e-37d8-4b87-bba2-330374892b49",
            before_submit=lambda idem,hashed: append_durable(durable,idem,hashed),
        )
    assert result == "nwan_789"
    assert len(captured) == 1
    req=captured[0]
    assert req.url.path == "/v1/videos/generations"
    assert req.headers["authorization"] == "Bearer placeholder-key"
    assert req.headers["idempotency-key"] == "apix-wan30-789"
    assert len(durable)==1
    assert durable[0][0]=="apix-wan30-789"
    assert len(durable[0][1])==64


async def append_durable(arr,idem,digest):
    arr.append((idem,digest))


@pytest.mark.asyncio
@pytest.mark.parametrize("response,expected", [
    (httpx.Response(402,json={"detail":"insufficient_balance"}),NeironychSeedanceError),
    (httpx.Response(503,json={"detail":"busy"}),NeironychSubmissionUnknown),
    (httpx.Response(202,text="not json"),NeironychSubmissionUnknown),
    (httpx.Response(202,json={"request_id":"accepted","client_request_id":"not-mine"}),NeironychSubmissionUnknown),
])
async def test_neironych_wan_post_classifies_known_and_unknown(response,expected):
    seen=[]
    async def handler(req):
        seen.append(req)
        return response
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler),base_url="https://example.test") as client:
        with pytest.raises(expected):
            await post_wan30_neironych(
                client=client,api_key="key",
                payload={"model":"wan-real-id","mode":"text","prompt":"hi"},
                idempotency_key="apix-wan30-789",
                client_request_id="d4496f2e-37d8-4b87-bba2-330374892b49",
                before_submit=lambda idem,hashed: append_durable([],idem,hashed),
            )
    assert len(seen)==1
