"""Role and actual provider-boundary regressions; no paid requests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import seedance25_adapter as s25
from api import video_service
from core.seedance_repeat_overrides import (
    build_seedance_repeat_prompt,
    build_seedance_repeat_reference_plan,
)


@pytest.mark.parametrize(
    "faces,clothing,expected_roles,index",
    [
        ([], "shirt", ["clothing"], 1),
        (["front"], "shirt", ["identity_primary", "clothing"], 2),
        (
            ["front", "side", "profile"],
            "shirt",
            ["identity_primary", "identity_support", "identity_support", "clothing"],
            4,
        ),
        (["front", "side"], None, ["identity_primary", "identity_support"], None),
    ],
)
def test_reference_plan_assigns_identity_before_clothing(faces, clothing, expected_roles, index):
    refs, count, actual_index, roles = build_seedance_repeat_reference_plan(
        faces, stored_roles=None, legacy_identity_transfer=True, clothing_reference_url=clothing
    )
    assert (refs, count, actual_index, roles) == (
        faces + ([clothing] if clothing else []),
        len(faces),
        index,
        expected_roles,
    )


def test_legacy_role_alignment_survives_duplicate_identity_urls():
    refs, count, index, roles = build_seedance_repeat_reference_plan(
        ["front", "front", "old-shirt"],
        stored_roles=["identity_primary", "identity_support", "clothing"],
        legacy_identity_transfer=False,
        clothing_reference_url="new-shirt",
    )
    assert (refs, count, index, roles) == (
        ["front", "new-shirt"],
        1,
        2,
        ["identity_primary", "clothing"],
    )


def test_reference_plan_rejects_identity_clothing_collision():
    with pytest.raises(ValueError):
        build_seedance_repeat_reference_plan(
            ["same"],
            stored_roles=["identity_primary"],
            legacy_identity_transfer=False,
            clothing_reference_url="same",
        )


def test_identity_only_edit_replaces_face_instead_of_keeping_content_unchanged():
    prompt = build_seedance_repeat_prompt("", identity_image_count=1)
    assert "Replace" in prompt and "facial identity" in prompt
    assert "Keep the visual content unchanged" not in prompt


@pytest.fixture
def provider(monkeypatch):
    async def unchanged(value):
        return value

    monkeypatch.setattr(video_service, "_prepare_video_reference_urls", unchanged)
    monkeypatch.setattr(video_service, "_prepare_reference_video_url", unchanged)
    monkeypatch.setattr(
        "api.video_runtime_fixes._validate_seedance_reference_video_url", AsyncMock()
    )
    create = AsyncMock(return_value={"code": 200, "data": {"taskId": "edit-task"}})
    monkeypatch.setattr(video_service.kieai_client, "create_task", create)
    return create


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 3])
async def test_content_edit_boundary_overrides_legacy_identity_token(provider, count):
    images = [f"https://example.test/face{i}.jpg" for i in range(count)] + [
        "https://example.test/shirt.jpg"
    ]
    roles = (["identity_primary"] + ["identity_support"] * (count - 1) if count else []) + [
        "clothing"
    ]
    await video_service.generate_video(
        video_service.VideoModel(s25.MODEL_KEY),
        "Replace requested attributes",
        image_url=images,
        reference_video_url="https://example.test/source.mp4",
        duration=7,
        resolution="480p",
        audio_ids=["__apix_seedance25:identity_transfer=true"],
        seedance_reference_roles=roles,
        seedance_content_edit={"number": "25", "clothing": "red cotton"},
    )
    payload = provider.await_args.args[0]
    inp = payload["input"]
    assert payload["model"] == s25.MODEL_KEY
    assert inp["reference_video_urls"] == ["https://example.test/source.mp4"]
    assert inp["reference_image_urls"] == images
    assert f"@Image{count+1} is the clothing" in inp["prompt"]
    assert "@Video1 is the authoritative source video" in inp["prompt"]
    assert 'must read exactly "25"' in inp["prompt"]
    assert (inp["duration"], inp["aspect_ratio"], inp["resolution"]) == (-1, "adaptive", "480p")


@pytest.mark.asyncio
async def test_video_token_without_actual_source_is_rejected(provider):
    with pytest.raises(ValueError, match="source video"):
        await video_service.generate_video(
            video_service.VideoModel(s25.MODEL_KEY),
            "Edit @Video1",
            image_url=["https://example.test/shirt.jpg"],
            seedance_reference_roles=["clothing"],
            seedance_content_edit={"number": "25", "clothing": ""},
        )
    provider.assert_not_awaited()


def test_genjutsu_menu_exposes_independent_face_clothing_flow():
    from bot.handlers.video_gen import _genjutsu_entry_markup

    markup = _genjutsu_entry_markup(
        [SimpleNamespace(model_key=s25.MODEL_KEY, credits=3, display_name="Seedance")],
        configured=False,
    )
    assert any(
        b.text == "🎭 Замена лица / одежды" and b.callback_data == "gjreplace:start"
        for row in markup.inline_keyboard
        for b in row
    )


@pytest.mark.parametrize(
    "images,roles",
    [
        (["front", "shirt"], ["identity_primary"]),
        (["front"], ["identity_unknown"]),
        (
            ["a", "b", "c", "d"],
            ["identity_primary", "identity_support", "identity_support", "identity_support"],
        ),
        (["same", "same"], ["identity_primary", "clothing"]),
    ],
)
def test_restore_rejects_ambiguous_roles(images, roles):
    from core.seedance_repeat_overrides import restore_seedance_reference_plan

    with pytest.raises(ValueError):
        restore_seedance_reference_plan(images, roles)


def test_legacy_identity_generation_restores_image_order_without_role_metadata():
    from core.seedance_repeat_overrides import restore_seedance_reference_plan

    plan = restore_seedance_reference_plan(["front", "side"], None, legacy_identity_transfer=True)
    assert (plan.image_urls, plan.roles) == (
        ("front", "side"),
        ("identity_primary", "identity_support"),
    )


def test_clothing_contract_does_not_copy_identity_motion_or_scene():
    from core.seedance_repeat_overrides import (
        build_seedance_content_edit_prompt,
        build_seedance_reference_plan,
    )

    prompt = build_seedance_content_edit_prompt(
        build_seedance_reference_plan([], "shirt"), {"number": "0025", "clothing": "red"}
    )
    assert 'must read exactly "0025"' in prompt
    assert "Preserve the main person's identity and face from @Video1" in prompt
    assert (
        "Do not copy the face, body identity, person, pose, body motion, background, framing, camera or lighting from @Image1"
        in prompt
    )
    assert "garment design, colors, materials, fit, visible logos and accessories" in prompt


def test_final_prompt_limit_includes_technical_roles():
    from api.video_prompt_limits import SEEDANCE_25_PROMPT_MAX_CHARS

    with pytest.raises(ValueError, match="30,000"):
        build_seedance_repeat_prompt(
            "x" * (SEEDANCE_25_PROMPT_MAX_CHARS - 10),
            identity_image_count=1,
            clothing_image_index=2,
        )


@pytest.mark.asyncio
async def test_provider_prompt_limit_is_enforced_after_role_instructions(provider, monkeypatch):
    monkeypatch.setattr("api.video_prompt_limits.SEEDANCE_25_PROMPT_MAX_CHARS", 100)
    with pytest.raises(ValueError):
        await video_service.generate_video(
            video_service.VideoModel(s25.MODEL_KEY),
            "edit",
            reference_video_url="https://example.test/source.mp4",
            image_url=["shirt"],
            seedance_reference_roles=["clothing"],
            seedance_content_edit={"clothing": "red"},
        )
    provider.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["images", "video"])
async def test_reference_upload_loss_never_creates_task(provider, monkeypatch, failure):
    if failure == "images":
        monkeypatch.setattr(
            video_service, "_prepare_video_reference_urls", AsyncMock(return_value=["one.jpg"])
        )
    else:
        monkeypatch.setattr(
            video_service, "_prepare_reference_video_url", AsyncMock(return_value=None)
        )
    with pytest.raises(ValueError):
        await video_service.generate_video(
            video_service.VideoModel(s25.MODEL_KEY),
            "edit",
            image_url=["face.jpg", "shirt.jpg"],
            reference_video_url="https://example.test/source.mp4",
            seedance_reference_roles=["identity_primary", "clothing"],
            seedance_content_edit={"number": "25"},
        )
    provider.assert_not_awaited()


def test_clothing_photo_without_text_explicitly_requests_outfit_replacement():
    from core.seedance_repeat_overrides import (
        build_seedance_content_edit_prompt,
        build_seedance_reference_plan,
    )

    prompt = build_seedance_content_edit_prompt(build_seedance_reference_plan([], "shirt"), {})
    assert "Replace the main person's outfit using @Image1" in prompt
