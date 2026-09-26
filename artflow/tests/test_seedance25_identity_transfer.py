from __future__ import annotations

from pathlib import Path

import pytest

from api import seedance25_adapter, video_service
from api.video_runtime_fixes import install_video_runtime_fixes
from bot.keyboards.models import video_mode_kb, video_params_kb


def _callbacks(markup) -> set[str]:
    return {
        str(button.callback_data)
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


def _texts(markup) -> list[str]:
    return [
        str(button.text)
        for row in markup.inline_keyboard
        for button in row
    ]


def test_identity_prompt_assigns_image_and_video_roles() -> None:
    from api.seedance25_identity import build_identity_transfer_prompt

    prompt = build_identity_transfer_prompt("keep her black jacket", image_count=1)

    assert "@Image1" in prompt
    assert "sole authoritative identity" in prompt
    assert "@Video1" in prompt
    assert "motion" in prompt
    assert "Do not inherit" in prompt
    assert "keep her black jacket" in prompt


def test_identity_prompt_uses_extra_images_only_as_same_person_evidence() -> None:
    from api.seedance25_identity import build_identity_transfer_prompt

    prompt = build_identity_transfer_prompt("", image_count=3)

    assert "@Image1" in prompt
    assert "@Image2" in prompt
    assert "@Image3" in prompt
    assert "primary identity" in prompt
    assert "same person" in prompt
    assert "head turns" in prompt
    assert "@Image4" not in prompt


@pytest.mark.parametrize(
    ("images", "videos", "message"),
    [
        ([], ["https://example.test/source.mp4"], "at least one identity photo"),
        (
            [
                "https://example.test/1.jpg",
                "https://example.test/2.jpg",
                "https://example.test/3.jpg",
                "https://example.test/4.jpg",
            ],
            ["https://example.test/source.mp4"],
            "at most 3 identity photos",
        ),
        (["https://example.test/1.jpg"], [], "one source video"),
        (
            ["https://example.test/1.jpg"],
            ["https://example.test/a.mp4", "https://example.test/b.mp4"],
            "one source video",
        ),
    ],
)
def test_identity_transfer_contract_rejects_ambiguous_media(
    images: list[str],
    videos: list[str],
    message: str,
) -> None:
    from api.seedance25_identity import validate_identity_transfer_refs

    with pytest.raises(ValueError, match=message):
        validate_identity_transfer_refs(images=images, videos=videos)


def test_identity_transfer_control_token_is_typed_option() -> None:
    _audios, _videos, options = seedance25_adapter._control_payload(
        [
            "__apix_seedance25:identity_transfer=true",
            "__apix_seedance25:generate_audio=false",
        ]
    )

    assert options["identity_transfer"] is True
    assert options["generate_audio"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("resolution", ["480p", "720p"])
async def test_identity_transfer_runtime_keeps_selected_resolution_and_assigns_roles(
    monkeypatch,
    resolution: str,
) -> None:
    install_video_runtime_fixes()
    calls: list[dict] = []

    async def create_task(payload, callback_url=None):
        calls.append(payload)
        return {"code": 200, "data": {"taskId": f"identity-{resolution}"}}

    async def prepare_images(value):
        return value

    async def prepare_video(value):
        return value

    async def validate_video(_url, *, video_edit=False):
        assert video_edit is True

    monkeypatch.setattr(video_service.kieai_client, "create_task", create_task)
    monkeypatch.setattr(video_service, "_prepare_video_reference_urls", prepare_images)
    monkeypatch.setattr(video_service, "_prepare_reference_video_url", prepare_video)
    monkeypatch.setattr(
        "api.video_runtime_fixes._validate_seedance_reference_video_url",
        validate_video,
    )

    await video_service.generate_video(
        video_service.VideoModel(seedance25_adapter.MODEL_KEY),
        "keep the source outfit",
        image_url=[
            "https://example.test/front.jpg",
            "https://example.test/three-quarter.jpg",
            "https://example.test/profile.jpg",
        ],
        reference_video_url=["https://example.test/source.mp4"],
        duration=30,
        aspect_ratio="9:16",
        resolution=resolution,
        audio_ids=[
            "__apix_seedance25:identity_transfer=true",
            "__apix_seedance25:generate_audio=false",
        ],
    )

    provider_input = calls[0]["input"]
    assert provider_input["resolution"] == resolution
    assert provider_input["aspect_ratio"] == "adaptive"
    assert provider_input["duration"] == -1
    assert provider_input["generate_audio"] is False
    assert provider_input["reference_image_urls"] == [
        "https://example.test/front.jpg",
        "https://example.test/three-quarter.jpg",
        "https://example.test/profile.jpg",
    ]
    assert provider_input["reference_video_urls"] == ["https://example.test/source.mp4"]
    assert "@Image1" in provider_input["prompt"]
    assert "@Image2" in provider_input["prompt"]
    assert "@Image3" in provider_input["prompt"]
    assert "@Video1" in provider_input["prompt"]
    assert "keep the source outfit" in provider_input["prompt"]


def test_telegram_seedance_identity_mode_and_quality_choices_are_explicit() -> None:
    mode_markup = video_mode_kb(seedance25_adapter.MODEL_KEY)
    assert f"vid_mode:identity:{seedance25_adapter.MODEL_KEY}" in _callbacks(mode_markup)
    assert any("Замена персонажа" in text for text in _texts(mode_markup))

    params = video_params_kb(
        seedance25_adapter.MODEL_KEY,
        30,
        "adaptive",
        "480p",
        selected_mode="image",
        ref_count=3,
        identity_transfer=True,
    )
    callbacks = _callbacks(params)
    assert "vpar_res:480p" in callbacks
    assert "vpar_res:720p" in callbacks
    assert not any(value.startswith("vpar_dur:") for value in callbacks)
    assert not any(value.startswith("vpar_ratio:") for value in callbacks)


def test_miniapp_seedance_identity_preset_is_user_selectable() -> None:
    source = Path("webapp/src/lib/seedance25-miniapp-enhancer.ts").read_text(encoding="utf-8")

    assert 'data-seedance25="identityTransfer"' in source
    assert 'token("identity_transfer", options.identityTransfer)' in source
    assert "1–3" in source
    assert "480p" in source and "720p" in source


def test_website_seedance_identity_preset_is_user_selectable() -> None:
    source = Path("landing/js/seedance25-studio.js").read_text(encoding="utf-8")

    assert "data-s25-identity-transfer" in source
    assert 'token("identity_transfer"' in source
    assert "1–3" in source
    assert "480p" in source and "720p" in source


def test_identity_transfer_uses_source_duration_for_telegram_preflight() -> None:
    from bot.handlers.video_gen import _video_upload_billable_duration

    assert _video_upload_billable_duration(
        {
            "model_key": seedance25_adapter.MODEL_KEY,
            "seedance_identity_transfer": True,
            "duration": 5,
        },
        video_duration=23,
        motion_step=None,
        is_genjutsu_video_mode=False,
    ) == 23


def test_identity_transfer_rejects_user_prompt_that_expands_past_provider_limit() -> None:
    from api.seedance25_identity import build_identity_transfer_prompt

    with pytest.raises(ValueError, match="30,000"):
        build_identity_transfer_prompt("x" * 30_000, image_count=3)


def test_identity_prompt_supports_structured_number_and_outfit_overrides() -> None:
    from api.seedance25_identity import build_identity_transfer_prompt

    prompt = build_identity_transfer_prompt(
        "",
        image_count=3,
        number_text="25",
        outfit_text="чёрная кожаная куртка",
    )

    assert "Number / digits: 25" in prompt
    assert "Clothing / outfit: чёрная кожаная куртка" in prompt
    assert "priority appearance changes" in prompt
    assert "@Image1" in prompt and "@Video1" in prompt


def test_identity_prompt_rejects_invalid_structured_overrides() -> None:
    from api.seedance25_identity import build_identity_transfer_prompt

    with pytest.raises(ValueError, match="number"):
        build_identity_transfer_prompt("", image_count=1, number_text="twenty five")

    with pytest.raises(ValueError, match="outfit"):
        build_identity_transfer_prompt("", image_count=1, outfit_text="x" * 161)


def test_identity_override_control_tokens_are_typed_options() -> None:
    _audios, _videos, options = seedance25_adapter._control_payload(
        [
            "__apix_seedance25:identity_transfer=true",
            "__apix_seedance25:identity_number=25",
            "__apix_seedance25:identity_outfit=black%20leather%20jacket",
        ]
    )

    assert options["identity_number"] == "25"
    assert options["identity_outfit"] == "black leather jacket"


def test_seedance_identity_surfaces_expose_number_and_clothing_fields() -> None:
    mini = Path("webapp/src/lib/seedance25-miniapp-enhancer.ts").read_text(encoding="utf-8")
    site = Path("landing/js/seedance25-studio.js").read_text(encoding="utf-8")
    bot = Path("bot/keyboards/models.py").read_text(encoding="utf-8")

    assert 'data-seedance25="identityNumber"' in mini
    assert 'data-seedance25="identityOutfit"' in mini
    assert 'token("identity_number"' in mini
    assert 'token("identity_outfit"' in mini

    assert "data-s25-identity-number" in site
    assert "data-s25-identity-outfit" in site
    assert 'token("identity_number"' in site
    assert 'token("identity_outfit"' in site

    assert "🎽 Одежда" in bot
    assert "🔢 Номер" in bot
