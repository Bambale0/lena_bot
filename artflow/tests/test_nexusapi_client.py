from __future__ import annotations

import json

import httpx
import pytest

from api.nexusapi_client import (
    NEXUS_NANO_BANANA_PRO_MODEL,
    NexusApiClient,
    NexusApiError,
    build_nano_banana_pro_params,
    extract_result_base64,
    extract_result_urls,
    find_model_in_catalog,
)


def test_build_nano_banana_pro_params_matches_documented_schema():
    payload = build_nano_banana_pro_params(
        prompt="make it cinematic",
        aspect_ratio="16:9",
        seed=123,
        image_url="https://cdn.example/ref.png",
        webhook_url="https://example.test/nexus-hook",
    )

    assert payload == {
        "model_name": "nano-banana-pro",
        "prompt": "make it cinematic",
        "aspect_ratio": "16:9",
        "seed": 123,
        "image_url": "https://cdn.example/ref.png",
        "webhook_url": "https://example.test/nexus-hook",
    }


def test_build_nano_banana_pro_params_rejects_undocumented_ratio():
    with pytest.raises(ValueError, match="aspect_ratio"):
        build_nano_banana_pro_params(prompt="test", aspect_ratio="21:9")


@pytest.mark.asyncio
async def test_create_uses_native_generate_contract_and_idempotency_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("Authorization")
        seen["idempotency"] = request.headers.get("Idempotency-Key")
        seen["json"] = json.loads(request.content.decode())
        return httpx.Response(202, json={"message": "Task accepted for processing", "task_id": "task-123"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://nexusapi.dev", transport=transport) as http_client:
        client = NexusApiClient(api_key="secret", client=http_client)
        created = await client.create_nano_banana_pro(
            prompt="premium product shot",
            aspect_ratio="1:1",
            seed=7,
            idempotency_key="12345678-test-key",
        )

    assert created.task_id == "task-123"
    assert created.status_code == 202
    assert seen == {
        "method": "POST",
        "path": "/generate",
        "authorization": "Bearer secret",
        "idempotency": "12345678-test-key",
        "json": {
            "params": {
                "model_name": NEXUS_NANO_BANANA_PRO_MODEL,
                "prompt": "premium product shot",
                "aspect_ratio": "1:1",
                "seed": 7,
            }
        },
    }


@pytest.mark.asyncio
async def test_wait_for_task_tracks_provider_lifecycle(monkeypatch):
    responses = iter(
        [
            {"task_id": "task-1", "status": "queued", "result": None},
            {"task_id": "task-1", "status": "processing", "result": None},
            {
                "task_id": "task-1",
                "status": "completed",
                "result": {"image_url": "https://cdn.nexusapi.dev/result.png"},
            },
        ]
    )
    client = NexusApiClient(api_key="secret")

    async def fake_get_task(task_id: str):
        assert task_id == "task-1"
        return next(responses)

    async def no_sleep(_seconds: float):
        return None

    monkeypatch.setattr(client, "get_task", fake_get_task)
    monkeypatch.setattr("api.nexusapi_client.asyncio.sleep", no_sleep)
    result = await client.wait_for_task("task-1", poll_interval=0.5, timeout_seconds=10)

    assert result.completed is True
    assert result.status_history == ("queued", "processing", "completed")
    assert extract_result_urls(result.payload) == ["https://cdn.nexusapi.dev/result.png"]


@pytest.mark.asyncio
async def test_provider_errors_preserve_http_status_and_detail():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"detail": "insufficient balance"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://nexusapi.dev", transport=transport) as http_client:
        client = NexusApiClient(api_key="secret", client=http_client)
        with pytest.raises(NexusApiError) as caught:
            await client.create_nano_banana_pro(prompt="test")

    assert caught.value.status_code == 402
    assert "insufficient balance" in str(caught.value)


def test_result_extractors_support_url_and_base64_shapes():
    payload = {
        "result": {
            "image_url": "https://cdn.example/a.png",
            "images": [
                {"url": "https://cdn.example/b.png"},
                {"b64_json": "aGVsbG8="},
            ],
        }
    }
    assert extract_result_urls(payload) == [
        "https://cdn.example/a.png",
        "https://cdn.example/b.png",
    ]
    assert extract_result_base64(payload) == [b"hello"]


def test_find_model_in_public_catalog():
    payload = {
        "models": [
            {"model_name": "nano-banana", "price": 0.8},
            {"model_name": "nano-banana-pro", "price": 2.2},
        ]
    }
    assert find_model_in_catalog(payload) == {"model_name": "nano-banana-pro", "price": 2.2}
