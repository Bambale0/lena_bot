"""WAN new paid tasks must never use the old KIE generic 3x POST retry."""
from unittest.mock import AsyncMock

import pytest

from api import kieai_client


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ("wan/3-0-video", "wan/3-0-video-prime"))
async def test_wan30_create_task_uses_only_the_single_post_transport(monkeypatch, model):
    safe = AsyncMock(return_value={"code":200,"data":{"taskId":"one-id"}})
    legacy_retry = AsyncMock()
    monkeypatch.setattr(kieai_client, "_create_task_once", safe)
    monkeypatch.setattr(kieai_client, "_retry_post", legacy_retry)
    out = await kieai_client.create_task({"model":model, "input":{"prompt":"Hi"}},callback_url="https://example.test/cb")
    assert out["data"]["taskId"]=="one-id"
    safe.assert_awaited_once()
    assert safe.await_args.args[0]["model"] == model
    assert safe.await_args.args[0]["callBackUrl"] == "https://example.test/cb"
    legacy_retry.assert_not_awaited()
