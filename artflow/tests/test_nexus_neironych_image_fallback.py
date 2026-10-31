from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import neironych_image_fallback_adapter as neironych_image_adapter
from api import nexus_neironych_image_fallback as fallback
from db.models import GenerationStatus, GenerationType


@pytest.mark.parametrize(("model_key", "expected"), [
    ("nano-banana-pro", "nano-banana-pro"),
    ("nano-banana-2", "nano-banana-2"),
    ("gpt-image-2-text-to-image", "gpt-image-2"),
    ("gpt-image-2-image-to-image", "gpt-image-2"),
])
def test_fallback_preserves_exact_model_and_references(model_key, expected):
    payload = neironych_image_adapter.build_fallback_image_payload(
        model_key=model_key, prompt="preserve character",
        image_urls=["https://example.test/ref.png"], aspect_ratio="9:16", quality="2K"
    )
    assert payload["model"] == expected
    assert payload["images"] == [{"image_url": "https://example.test/ref.png"}]
    assert payload["aspect_ratio"] == "9:16"
    assert payload["response_format"] == "b64_json"
    if expected == "gpt-image-2":
        assert "resolution" not in payload
    else:
        assert payload["resolution"] == "2k"


@pytest.mark.parametrize("model", ["nano-banana-pro-vip", "gpt-image-2-vip", "seedream/5-pro-text-to-image"])
def test_fallback_never_substitutes_unsupported_models(model):
    with pytest.raises(ValueError, match="Unsupported"):
        neironych_image_adapter.build_fallback_image_payload(model_key=model, prompt="test")


def generation(model="nano-banana-pro", suffix="123"):
    return SimpleNamespace(
        id=int(suffix), model=model, gen_type=GenerationType.image,
        status=GenerationStatus.processing, task_id=f"nexus:task_{suffix}",
        prompt="portrait", input_params=json.dumps({
            "img_count": 1, "img_ratio": "1:1", "img_quality": "2K",
            "reference_images": ["https://example.test/ref.png"],
        }),
    )


@pytest.mark.asyncio
async def test_terminal_e294_claims_and_schedules_once(monkeypatch):
    gen = generation()
    claim = AsyncMock(return_value=True)
    monkeypatch.setattr(fallback, "fallback_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(fallback.repo, "claim_nexus_image_fallback", claim)
    scheduled = []
    monkeypatch.setattr(fallback, "_spawn_image_fallback", lambda *args: scheduled.append(args))

    accepted = await fallback.maybe_start_image_fallback(
        object(), gen, {"task_id": "task_123", "status": "failed", "error": "E-294 high load"}
    )
    assert accepted is True
    claim.assert_awaited_once()
    assert scheduled == [(123, claim.await_args.kwargs["fallback_task_id"])]


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "error"), [
    ("failed", "Safety filter blocked"),
    ("failed", "Content policy violation"),
    ("processing", "E-294"),
    ("failed", "No images found"),
])
async def test_never_fallback_on_moderation_or_nonterminal(monkeypatch, status, error):
    monkeypatch.setattr(fallback, "fallback_enabled", AsyncMock(return_value=True))
    claim = AsyncMock(return_value=True)
    monkeypatch.setattr(fallback.repo, "claim_nexus_image_fallback", claim)
    assert await fallback.maybe_start_image_fallback(
        object(), generation(), {"task_id": "task_123", "status": status, "error": error}
    ) is False
    claim.assert_not_awaited()


@pytest.mark.asyncio
async def test_losing_claim_prevents_duplicate_paid_post(monkeypatch):
    monkeypatch.setattr(fallback, "fallback_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(fallback.repo, "claim_nexus_image_fallback", AsyncMock(return_value=False))
    scheduled = []
    monkeypatch.setattr(fallback, "_spawn_image_fallback", lambda *args: scheduled.append(args))
    assert await fallback.maybe_start_image_fallback(
        object(), generation(model="nano-banana-2"),
        {"task_id": "task_123", "status": "failed", "error": "E-294"}
    ) is False
    assert scheduled == []


@pytest.mark.asyncio
async def test_unverified_task_identity_never_falls_back(monkeypatch):
    monkeypatch.setattr(fallback, "fallback_enabled", AsyncMock(return_value=True))
    claim = AsyncMock(return_value=True)
    monkeypatch.setattr(fallback.repo, "claim_nexus_image_fallback", claim)
    assert await fallback.maybe_start_image_fallback(
        object(), generation(), {"task_id": "somebody-else", "status": "failed", "error": "E-294"}
    ) is False
    claim.assert_not_awaited()


@pytest.mark.asyncio
async def test_vip_model_refuses_fallback_even_on_e294(monkeypatch):
    claim = AsyncMock(return_value=True)
    monkeypatch.setattr(fallback.repo, "claim_nexus_image_fallback", claim)
    assert await fallback.maybe_start_image_fallback(
        object(), generation(model="nano-banana-pro-vip"),
        {"task_id": "task_123", "status": "failed", "error": "E-294"}
    ) is False
    claim.assert_not_awaited()


from core import image_fallback_policy as image_policy
from db.models import ProviderRoutingAudit


@pytest.mark.asyncio
async def test_fallback_routing_admin_can_disable_and_audit(monkeypatch):
    from unittest.mock import MagicMock

    row = SimpleNamespace(primary_provider="neironych", updated_by_admin_tg_id=None)
    fake = SimpleNamespace(
        execute=AsyncMock(side_effect=[
            None, SimpleNamespace(scalar_one=lambda: row),
        ]),
        add=MagicMock(), commit=AsyncMock(),
    )
    change = await image_policy.set_image_fallback_route(
        fake, "nano-banana-pro", False, admin_tg_id=42,
    )
    assert change.enabled is False
    assert row.primary_provider == "nexus"
    audit = fake.add.call_args.args[0]
    assert isinstance(audit, ProviderRoutingAudit)
    assert audit.model_key == "image-fallback:nano-banana-pro"
    assert audit.previous_provider == "neironych"
    assert audit.new_provider == "nexus"
    assert audit.changed_by_admin_tg_id == 42


@pytest.mark.asyncio
async def test_fallback_admin_default_is_enabled_without_db_setting():
    session = SimpleNamespace(get=AsyncMock(return_value=None))
    route = await image_policy.get_image_fallback_route(session, "nano-banana-pro")
    assert route.enabled and route.fallback_provider == "neironych"
    assert route.source == "default"


@pytest.mark.asyncio
async def test_fallback_admin_unsupported_model_does_not_touch_database():
    session = SimpleNamespace(get=AsyncMock())
    assert not await image_policy.fallback_enabled(session, "nano-banana-pro-vip")
    session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_fallback_routing_admin_requires_real_actor():
    with pytest.raises(ValueError, match="Admin actor"):
        await image_policy.set_image_fallback_route(
            SimpleNamespace(), "nano-banana-pro", True, admin_tg_id=0,
        )
