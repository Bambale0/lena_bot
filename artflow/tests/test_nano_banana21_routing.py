from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import image_service, neironych_image_adapter, nexus_image_adapter
from api.image_service import ImageModel
from api.provider_contract_catalog import IMAGE_CONTRACTS
from bot.keyboards.models import IMAGE_CAPS, NANA_BANANO_MODEL_CHOICES
from bot.ui.model_labels import model_display_name
from db.seed import derive_nano_banana_21_prices


def test_nano_banana_21_is_a_distinct_model_on_all_surfaces():
    model = ImageModel.NANO_BANANA_21
    assert model.value == "nano-banana-2.1"
    assert model in IMAGE_CAPS
    assert IMAGE_CAPS[model]["max_refs"] == 4
    assert IMAGE_CAPS[model]["quality_options"] == [("1K", "1K"), ("2K", "2K"), ("4K", "4K")]
    assert model.value in NANA_BANANO_MODEL_CHOICES
    assert model_display_name(model.value) == "🍌 Nano Banana 2.1"
    assert any(c.model == model.value for c in IMAGE_CONTRACTS)


def test_neironych_21_contract_preserves_quality_and_references():
    payload = neironych_image_adapter.build_nano_banana21_payload(
        prompt="Edit the shirt only",
        image_urls=["https://example.test/a.png", "https://example.test/b.png"],
        aspect_ratio="4:3",
        quality="4K",
    )
    assert payload == {
        "model": "nano-banana-2.1",
        "prompt": "Edit the shirt only",
        "n": 1,
        "images": [
            {"image_url": "https://example.test/a.png"},
            {"image_url": "https://example.test/b.png"},
        ],
        "aspect_ratio": "4:3",
        "resolution": "4k",
        "response_format": "b64_json",
    }


def test_neironych_21_rejects_invalid_ratio_and_too_many_refs():
    with pytest.raises(ValueError, match="aspect ratio"):
        neironych_image_adapter.build_nano_banana21_payload(
            prompt="Test", aspect_ratio="42:1", quality="2K"
        )
    with pytest.raises(ValueError, match="at most 4"):
        neironych_image_adapter.build_nano_banana21_payload(
            prompt="Test",
            image_urls=[f"https://example.test/{i}.png" for i in range(5)],
            quality="2K",
        )


def test_nexus_21_contract_preserves_exact_model_and_quality():
    params = nexus_image_adapter.build_nexus_image_params(
        model_key="nano-banana-2.1",
        prompt="Product photography",
        image_urls=["https://example.test/ref.png"],
        aspect_ratio="1:4",
        quality="4K",
    )
    assert params == {
        "model_name": "nano-banana-2.1",
        "prompt": "Product photography",
        "image_urls": ["https://example.test/ref.png"],
        "aspect_ratio": "1:4",
        "image_size": "4K",
    }


@pytest.mark.asyncio
async def test_primary_neironych_21_returns_saved_image_url(monkeypatch):
    primary = AsyncMock(return_value="https://static.example.test/generated/21.jpg")
    nexus = AsyncMock(side_effect=AssertionError("primary succeeded; fallback must not run"))
    monkeypatch.setattr(image_service.settings, "NANO_BANANA_21_PRIMARY_PROVIDER", "neironych")
    monkeypatch.setattr(image_service.neironych_image_adapter, "generate_nano_banana21_image", primary)
    monkeypatch.setattr(image_service.nexus_image_adapter, "create_nexus_image_task", nexus)

    result = await image_service.generate_image(
        ImageModel.NANO_BANANA_21,
        "White dog in a red scarf",
        image_url=["https://example.test/ref.png"],
        aspect_ratio="16:9",
        quality="2K",
    )

    assert result.is_async is False
    assert result.url == "https://static.example.test/generated/21.jpg"
    assert result.provider == "neironych"
    assert primary.await_args.kwargs["image_urls"] == ["https://example.test/ref.png"]
    nexus.assert_not_awaited()


@pytest.mark.asyncio
async def test_nexus_fallback_only_after_definitive_primary_rejection(monkeypatch):
    primary = AsyncMock(side_effect=neironych_image_adapter.NeironychImageRejected("rate limited", status_code=429))
    nexus = AsyncMock(return_value="nexus:exact-21-task")
    monkeypatch.setattr(image_service.settings, "NANO_BANANA_21_PRIMARY_PROVIDER", "neironych")
    monkeypatch.setattr(image_service.neironych_image_adapter, "generate_nano_banana21_image", primary)
    monkeypatch.setattr(image_service.nexus_image_adapter, "create_nexus_image_task", nexus)

    result = await image_service.generate_image(
        ImageModel.NANO_BANANA_21,
        "Studio photograph",
        aspect_ratio="1:1",
        quality="4K",
    )

    assert result.is_async is True
    assert result.provider == "nexus"
    assert result.task_id == "nexus:exact-21-task"
    assert nexus.await_args.kwargs["model_key"] == "nano-banana-2.1"


@pytest.mark.asyncio
async def test_no_fallback_for_ambiguous_neironych_failure(monkeypatch):
    primary = AsyncMock(side_effect=neironych_image_adapter.NeironychImageError("outcome unknown"))
    nexus = AsyncMock()
    monkeypatch.setattr(image_service.settings, "NANO_BANANA_21_PRIMARY_PROVIDER", "neironych")
    monkeypatch.setattr(image_service.neironych_image_adapter, "generate_nano_banana21_image", primary)
    monkeypatch.setattr(image_service.nexus_image_adapter, "create_nexus_image_task", nexus)
    with pytest.raises(neironych_image_adapter.NeironychImageError):
        await image_service.generate_image(ImageModel.NANO_BANANA_21, "Test image")
    nexus.assert_not_awaited()


def test_initial_21_prices_are_cloned_from_current_admin_prices():
    source = [
        SimpleNamespace(model_key="nano-banana-2", credits=1.7, gen_type="image", is_active=True),
        SimpleNamespace(model_key="nano-banana-2__quality=2K", credits=1.8, gen_type="image", is_active=True),
        SimpleNamespace(model_key="nano-banana-2__quality=4K", credits=2.9, gen_type="image", is_active=True),
    ]
    added = derive_nano_banana_21_prices(source)
    assert [(c["model_key"], c["credits"]) for c in added] == [
        ("nano-banana-2.1", 1.7),
        ("nano-banana-2.1__quality=2K", 1.8),
        ("nano-banana-2.1__quality=4K", 2.9),
    ]
    already_configured = source + [SimpleNamespace(model_key="nano-banana-2.1", credits=7.0, gen_type="image", is_active=True)]
    assert all(row["model_key"] != "nano-banana-2.1" for row in derive_nano_banana_21_prices(already_configured))

@pytest.mark.asyncio
async def test_neironych_client_uses_idempotency_header_and_saves_stable_url(monkeypatch):
    import base64
    import io
    import json

    import httpx
    from PIL import Image

    with io.BytesIO() as buffer:
        Image.new("RGB", (4, 4), "green").save(buffer, format="JPEG")
        valid_image = buffer.getvalue()

    seen = []
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"created": 123, "data": [{"b64_json": base64.b64encode(valid_image).decode()}]},
        )
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        neironych_image_adapter.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    saved = []
    monkeypatch.setattr(
        neironych_image_adapter, "save_public_file",
        lambda data, **kwargs: saved.append((data, kwargs)) or "https://static.test/generated.jpg",
    )
    monkeypatch.setattr(neironych_image_adapter.settings, "NEIRONYCH_API_KEY", "test-key")
    monkeypatch.setattr(
        neironych_image_adapter.settings, "NEIRONYCH_API_BASE_URL", "https://api.example.test"
    )

    url = await neironych_image_adapter.generate_nano_banana21_image(
        prompt="Keep the same cat",
        image_urls=["https://example.test/ref1.jpg"],
        aspect_ratio="9:16",
        quality="2K",
    )
    assert url == "https://static.test/generated.jpg"
    assert len(seen) == 1
    assert seen[0].url.path == "/v1/images/edits"
    assert seen[0].headers["Idempotency-Key"] == seen[0].headers["X-Client-Request-Id"]
    assert seen[0].headers["Authorization"] == "Bearer test-key"
    payload = json.loads(seen[0].content)
    assert payload["model"] == "nano-banana-2.1"
    assert payload["resolution"] == "2k"
    assert payload["images"] == [{"image_url": "https://example.test/ref1.jpg"}]
    assert saved[0][0] == valid_image


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (429, {"error": {"code": "provider_rate_limited"}}, neironych_image_adapter.NeironychImageRejected),
        (422, {"error": {"code": "invalid_reference_images"}}, neironych_image_adapter.NeironychImageError),
        (503, {"error": {"code": "submission_outcome_unknown"}}, neironych_image_adapter.NeironychImageError),
        (200, {"data": [{"url": "https://example.test/temporary.jpg"}]}, neironych_image_adapter.NeironychImageError),
    ],
)
async def test_neironych_image_http_failures_are_classified_for_safe_fallback(
    monkeypatch, status, body, expected
):
    import httpx

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    monkeypatch.setattr(
        neironych_image_adapter.httpx, "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    monkeypatch.setattr(neironych_image_adapter.settings, "NEIRONYCH_API_KEY", "test-key")
    monkeypatch.setattr(
        neironych_image_adapter.settings, "NEIRONYCH_API_BASE_URL", "https://api.example.test"
    )
    with pytest.raises(expected) as info:
        await neironych_image_adapter.generate_nano_banana21_image(prompt="test")
    if status == 503:
        assert type(info.value) is neironych_image_adapter.NeironychImageError
    if status == 422:
        assert type(info.value) is neironych_image_adapter.NeironychImageError


@pytest.mark.asyncio
async def test_neironych_timeout_is_never_a_definitive_rejection(monkeypatch):
    import httpx

    def timeout(request):
        raise httpx.ReadTimeout("simulated timeout", request=request)

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(timeout)
    monkeypatch.setattr(
        neironych_image_adapter.httpx, "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    monkeypatch.setattr(neironych_image_adapter.settings, "NEIRONYCH_API_KEY", "test-key")
    monkeypatch.setattr(
        neironych_image_adapter.settings, "NEIRONYCH_API_BASE_URL", "https://api.example.test"
    )
    with pytest.raises(neironych_image_adapter.NeironychImageError) as info:
        await neironych_image_adapter.generate_nano_banana21_image(prompt="test")
    assert type(info.value) is neironych_image_adapter.NeironychImageError
    assert "outcome unknown" in str(info.value)


@pytest.mark.asyncio
async def test_miniapp_lists_nano_banana21_with_ref_ratio_and_quality_controls(monkeypatch):
    from api import miniapp_routes
    from db.models import GenerationType

    cost = SimpleNamespace(
        model_key="nano-banana-2.1",
        display_name="🍌 Nano Banana 2.1",
        credits=1.0,
        is_active=True,
        gen_type=GenerationType.image,
    )
    monkeypatch.setattr(miniapp_routes.repo, "get_all_model_costs", AsyncMock(return_value=[cost]))
    monkeypatch.setattr(
        miniapp_routes,
        "_resolve_image_quality_prices",
        AsyncMock(return_value={"1K": 1, "2K": 1, "4K": 1.5}),
    )
    models = await miniapp_routes.list_image_models(
        session=object(), user=SimpleNamespace(id=1)
    )
    assert len(models) == 1
    model = models[0]
    assert model.key == "nano-banana-2.1"
    assert model.max_refs == 4
    assert model.modes == ["text", "image"]
    assert model.counts == [1]
    assert [q["value"] for q in model.quality_options] == ["1K", "2K", "4K"]
    assert model.quality_prices["4K"] == 1.5


@pytest.mark.asyncio
async def test_website_public_model_catalog_includes_nano_banana21(monkeypatch):
    from api.web import models as web_models
    from db.models import GenerationType

    cost = SimpleNamespace(
        id=777,
        model_key="nano-banana-2.1",
        display_name="🍌 Nano Banana 2.1",
        credits=1.0,
        is_active=True,
        gen_type=GenerationType.image,
    )
    monkeypatch.setattr(web_models.repo, "get_all_model_costs", AsyncMock(return_value=[cost]))
    response = await web_models.models(session=object())
    assert response["data"]["image"][0]["model_key"] == "nano-banana-2.1"


def test_telegram_banana_keyboard_displays_version_21():
    from bot.keyboards.models import image_nana_banano_kb

    keyboard = image_nana_banano_kb("nano-banana-2.1")
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert any("Nano Banana 2.1" in text for text in labels)


@pytest.mark.asyncio
async def test_neironych_image_rejects_insecure_api_base_before_sending_key(monkeypatch):
    monkeypatch.setattr(neironych_image_adapter.settings, "NEIRONYCH_API_KEY", "secret-value")
    monkeypatch.setattr(neironych_image_adapter.settings, "NEIRONYCH_API_BASE_URL", "http://example.test")
    with pytest.raises(ValueError, match="HTTPS"):
        await neironych_image_adapter.generate_nano_banana21_image(prompt="test")


@pytest.mark.asyncio
async def test_neironych_explicit_correlation_id_is_sent_to_both_headers(monkeypatch):
    import base64
    import io

    import httpx
    from PIL import Image

    with io.BytesIO() as buffer:
        Image.new("RGB", (4, 4), "green").save(buffer, format="PNG")
        valid_image = buffer.getvalue()
    headers_seen = []
    transport = httpx.MockTransport(lambda req: (
        headers_seen.append(req.headers),
        httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(valid_image).decode()}]}),
    )[1])
    original_client = httpx.AsyncClient
    monkeypatch.setattr(neironych_image_adapter.httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))
    monkeypatch.setattr(neironych_image_adapter.settings, "NEIRONYCH_API_KEY", "dummy")
    monkeypatch.setattr(neironych_image_adapter.settings, "NEIRONYCH_API_BASE_URL", "https://provider.test")
    monkeypatch.setattr(neironych_image_adapter, "save_public_file", lambda data, **kw: "https://apix.test/image.png")
    rid = "d9307625-cff7-4341-8280-5a778154ccef"
    assert await neironych_image_adapter.generate_nano_banana21_image(
        prompt="test", request_id=rid
    ) == "https://apix.test/image.png"
    assert headers_seen[0]["Idempotency-Key"] == rid
    assert headers_seen[0]["X-Client-Request-Id"] == rid


@pytest.mark.asyncio
async def test_neironych_invalid_image_bytes_preserve_ambiguous_outcome(monkeypatch):
    import base64

    import httpx
    payload = base64.b64encode(b"not a valid image").decode()
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"data": [{"b64_json": payload}]}))
    monkeypatch.setattr(neironych_image_adapter.httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))
    monkeypatch.setattr(neironych_image_adapter.settings, "NEIRONYCH_API_KEY", "dummy")
    monkeypatch.setattr(neironych_image_adapter.settings, "NEIRONYCH_API_BASE_URL", "https://provider.test")
    saved = []
    monkeypatch.setattr(neironych_image_adapter, "save_public_file", lambda data, **kwargs: saved.append(data))
    with pytest.raises(neironych_image_adapter.NeironychImageError) as error:
        await neironych_image_adapter.generate_nano_banana21_image(prompt="test")
    assert type(error.value) is neironych_image_adapter.NeironychImageError
    assert not saved


def test_neironych_image_task_id_round_trip():
    rid = neironych_image_adapter.client_request_id_for_generation(123)
    assert len(rid) == 36
    task_id = neironych_image_adapter.encode_task_id(rid)
    assert task_id.startswith("neironych-image:")
    assert neironych_image_adapter.decode_task_id("web:" + task_id) == rid


@pytest.mark.asyncio
async def test_reconcile_unknown_neironych_image_never_refunds(monkeypatch):
    import uuid

    from api import miniapp_routes
    from db.models import GenerationStatus, GenerationType

    rid = str(uuid.uuid4())
    gen = SimpleNamespace(
        id=314, user_id=8, status=GenerationStatus.processing,
        model="nano-banana-2.1", gen_type=GenerationType.image,
        task_id=f"neironych-image:{rid}", created_at=None,
        image_session_id=None, input_params=None,
    )
    monkeypatch.setattr(miniapp_routes.neironych_image_adapter, "fetch_nano_banana21_status",
                        AsyncMock(return_value={"status": "reconciliation_required", "result_url": None}))
    refund = AsyncMock(side_effect=AssertionError("must not refund uncertain paid work"))
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", refund)
    result = await miniapp_routes._reconcile_generation_status(session=object(), gen=gen)
    assert result is gen
    refund.assert_not_awaited()

@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("http_status", "payload", "expected_state", "expected_url"),
    [
        (200, {"model_slug": "nano-banana-2.1", "status": "completed",
               "result_url": "https://cdn.example.test/result.png"}, "completed",
         "https://cdn.example.test/result.png"),
        (200, {"model_slug": "nano-banana-2.1", "status": "reconciliation_required",
               "result_url": None}, "reconciliation_required", None),
        (200, {"model_slug": "nano-banana-2.1", "status": "completed",
               "result_url": None}, "completed", None),
        (404, {"detail": "generation_not_found"}, "not_found", None),
    ],
)
async def test_provider_status_lookup_never_submits_paid_post(
    monkeypatch, http_status, payload, expected_state, expected_url
):
    import httpx

    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(http_status, json=payload)
    orig = httpx.AsyncClient
    monkeypatch.setattr(
        neironych_image_adapter.httpx, "AsyncClient",
        lambda **kw: orig(transport=httpx.MockTransport(respond), **kw)
    )
    monkeypatch.setattr(neironych_image_adapter.settings, "NEIRONYCH_API_BASE_URL", "https://provider.test")
    monkeypatch.setattr(neironych_image_adapter.settings, "NEIRONYCH_API_KEY", "test-key")
    rid = "d9307625-cff7-4341-8280-5a778154ccef"
    result = await neironych_image_adapter.fetch_nano_banana21_status(rid)
    assert result["status"] == expected_state
    assert result["result_url"] == expected_url
    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert seen[0].headers["Authorization"] == "Bearer test-key"
    assert seen[0].url.path.endswith(f"by-client-request-id/{rid}")


@pytest.mark.asyncio
async def test_provider_status_does_not_accept_mismatched_model(monkeypatch):
    import httpx

    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "model_slug": "another-model", "status": "completed",
        "result_url": "https://cdn.example.test/wrong.png",
    }))
    monkeypatch.setattr(neironych_image_adapter.httpx, "AsyncClient",
                        lambda **kw: original(transport=transport, **kw))
    monkeypatch.setattr(neironych_image_adapter.settings, "NEIRONYCH_API_BASE_URL", "https://provider.test")
    monkeypatch.setattr(neironych_image_adapter.settings, "NEIRONYCH_API_KEY", "test-key")
    with pytest.raises(neironych_image_adapter.NeironychImageError, match="Invalid reconciliation"):
        await neironych_image_adapter.fetch_nano_banana21_status("d9307625-cff7-4341-8280-5a778154ccef")
