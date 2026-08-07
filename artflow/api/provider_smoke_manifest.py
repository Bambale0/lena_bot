"""Executable live-smoke request templates for every provider contract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.provider_contract_catalog import ALL_CONTRACTS


@dataclass(frozen=True)
class SmokeCase:
    contract_id: str
    params: dict[str, Any]
    terminal_timeout_seconds: int = 900


IMAGE_URL = "${SMOKE_IMAGE_URL}"
IMAGE_2_URL = "${SMOKE_IMAGE_2_URL}"
VIDEO_URL = "${SMOKE_VIDEO_URL}"
AUDIO_URL = "${SMOKE_AUDIO_URL}"
TASK_ID = "${SMOKE_PROVIDER_TASK_ID}"
AUDIO_ID = "${SMOKE_SUNO_AUDIO_ID}"
MJ_TASK_ID = "${SMOKE_MJ_TASK_ID}"
MJ_CUSTOM_ID = "${SMOKE_MJ_CUSTOM_ID}"
CALLBACK_URL = "${SMOKE_CALLBACK_URL}"
IMAGE_BASE64 = "${SMOKE_IMAGE_BASE64}"


def _base_case(contract_id: str) -> dict[str, Any]:
    if contract_id.startswith("image."):
        params: dict[str, Any] = {"prompt": "APIX provider contract smoke test"}
        contract = next(item for item in ALL_CONTRACTS if item.contract_id == contract_id)
        if contract.modes == ("image",) or contract_id in {
            "image.wan27",
            "image.wan27.pro",
            "image.nano2",
            "image.nano2.lite",
            "image.nano.pro",
            "image.gpt2.i2i",
        }:
            params["image_url"] = IMAGE_URL
        return params

    primary_video: dict[str, dict[str, Any]] = {
        "video.kling26.t2v": {"prompt": "A paper airplane crosses a bright studio", "duration": 5, "aspect_ratio": "16:9"},
        "video.kling26.i2v": {"prompt": "Animate the paper airplane", "image_urls": [IMAGE_URL], "duration": 5},
        "video.kling26.motion": {"prompt": "Follow the reference motion", "image_url": IMAGE_URL, "video_url": VIDEO_URL, "mode": "720p"},
        "video.kling30": {"prompt": "A cinematic product reveal", "duration": 5, "mode": "std", "aspect_ratio": "16:9"},
        "video.kling30.motion": {"prompt": "Follow the reference motion", "image_url": IMAGE_URL, "video_url": VIDEO_URL, "mode": "720p"},
        "video.klingv3.turbo.t2v": {"prompt": "A fast city timelapse", "duration": 5, "aspect_ratio": "16:9", "resolution": "720p"},
        "video.klingv3.turbo.i2v": {"prompt": "Animate the scene", "image_urls": [IMAGE_URL], "duration": 5, "resolution": "720p"},
        "video.wan27.t2v": {"prompt": "A calm ocean at dawn", "duration": 5, "resolution": "720p", "aspect_ratio": "16:9"},
        "video.wan27.i2v": {"prompt": "Animate the ocean", "first_frame_url": IMAGE_URL, "duration": 5, "resolution": "720p"},
        "video.seedance2": {"prompt": "A dancer in a clean studio", "duration": 5, "resolution": "720p", "aspect_ratio": "16:9"},
        "video.seedance2.fast": {"prompt": "A dancer in a clean studio", "duration": 5, "resolution": "720p", "aspect_ratio": "16:9"},
        "video.seedance2.mini": {"prompt": "A dancer in a clean studio", "duration": 5, "resolution": "720p", "aspect_ratio": "16:9"},
        "video.seedance25": {"prompt": "A dancer in a clean studio", "duration": 5, "resolution": "720p", "aspect_ratio": "16:9"},
        "video.grok.t2v": {"prompt": "A playful robot waves", "duration": 6, "resolution": "480p", "aspect_ratio": "16:9"},
        "video.grok.i2v": {"prompt": "Animate the robot", "image_url": IMAGE_URL, "source_task_id": TASK_ID, "duration": 6, "resolution": "480p", "aspect_ratio": "16:9"},
        "video.happyhorse.t2v": {"prompt": "A horse runs through a field", "duration": 5, "resolution": "720p", "aspect_ratio": "16:9"},
        "video.happyhorse.i2v": {"prompt": "Animate the horse", "image_urls": [IMAGE_URL], "duration": 5, "resolution": "720p"},
        "video.gemini.omni": {"prompt": "A simple product animation", "duration": 4, "resolution": "720p", "aspect_ratio": "16:9"},
        "video.veo3": {"prompt": "A paper boat on a calm stream", "aspect_ratio": "16:9"},
        "video.veo3.fast": {"prompt": "A paper boat on a calm stream", "aspect_ratio": "16:9"},
        "video.veo3.lite": {"prompt": "A paper boat on a calm stream", "aspect_ratio": "16:9"},
    }
    if contract_id in primary_video:
        return primary_video[contract_id]

    advanced_video: dict[str, dict[str, Any]] = {
        "video.wan27.r2v": {"prompt": "Character one walks", "reference_image_urls": [IMAGE_URL], "duration": 5, "resolution": "720p", "aspect_ratio": "16:9"},
        "video.wan27.edit": {"prompt": "Change the lighting", "video_url": VIDEO_URL, "resolution": "720p", "aspect_ratio": "16:9"},
        "video.happyhorse.r2v": {"prompt": "Character one waves", "reference_image_urls": [IMAGE_URL], "duration": 5, "resolution": "720p", "aspect_ratio": "16:9"},
        "video.happyhorse.edit": {"prompt": "Change the background", "video_url": VIDEO_URL, "reference_image_urls": [IMAGE_URL], "resolution": "720p"},
        "video.happyhorse11.t2v": {"prompt": "A soft camera orbit", "duration": 5, "resolution": "720p", "aspect_ratio": "16:9"},
        "video.happyhorse11.i2v": {"prompt": "Animate the image", "image_urls": [IMAGE_URL], "duration": 5, "resolution": "720p"},
        "video.happyhorse11.r2v": {"prompt": "Character one turns", "reference_image_urls": [IMAGE_URL], "duration": 5, "resolution": "720p", "aspect_ratio": "16:9"},
        "video.grok.upscale": {"task_id": TASK_ID},
        "video.grok.extend": {"task_id": TASK_ID, "prompt": "Continue naturally", "extend_at": 2, "extend_times": 6},
        "video.grok.preview15": {"prompt": "A dramatic reveal", "aspect_ratio": "16:9", "resolution": "480p", "duration": 8},
        "video.veo.extend": {"task_id": TASK_ID, "prompt": "Continue the camera movement"},
        "video.veo.1080": {"task_id": TASK_ID, "index": 0},
        "video.veo.4k": {"task_id": TASK_ID, "index": 0},
    }
    if contract_id in advanced_video:
        return advanced_video[contract_id]

    suno: dict[str, dict[str, Any]] = {
        "suno.generate": {"prompt": "A short upbeat instrumental", "model": "V5", "instrumental": True},
        "suno.extend": {"audio_id": AUDIO_ID},
        "suno.upload-cover": {"upload_url": AUDIO_URL, "prompt": "Turn this into jazz", "model": "V5"},
        "suno.upload-extend": {"upload_url": AUDIO_URL, "prompt": "Continue naturally", "continue_at": 30, "model": "V5"},
        "suno.add-instrumental": {"upload_url": AUDIO_URL, "title": "Smoke instrumental", "tags": "jazz, piano", "model": "V4_5PLUS"},
        "suno.add-vocals": {"upload_url": AUDIO_URL, "prompt": "[Verse] Hello", "style": "Pop", "title": "Smoke vocals", "model": "V4_5PLUS"},
        "suno.replace-section": {"task_id": TASK_ID, "audio_id": AUDIO_ID, "prompt": "Replacement", "tags": "Pop", "title": "Smoke", "infill_start_s": 10, "infill_end_s": 20},
        "suno.persona": {"task_id": TASK_ID, "audio_id": AUDIO_ID, "name": "Smoke persona", "description": "Provider smoke persona"},
        "suno.mashup": {"upload_urls": [AUDIO_URL, "${SMOKE_AUDIO_2_URL}"], "prompt": "Blend both tracks", "model": "V5"},
        "suno.lyrics": {"prompt": "A short song about summer"},
        "suno.timestamped-lyrics": {"task_id": TASK_ID, "audio_id": AUDIO_ID},
        "suno.style": {"content": "Pop, cinematic, warm"},
        "suno.cover-art": {"task_id": TASK_ID},
        "suno.wav": {"task_id": TASK_ID, "audio_id": AUDIO_ID},
        "suno.stems": {"task_id": TASK_ID, "audio_id": AUDIO_ID, "separation_type": "separate_vocal"},
        "suno.midi": {"separation_task_id": TASK_ID, "callback_url": CALLBACK_URL},
        "suno.music-video": {"task_id": TASK_ID, "audio_id": AUDIO_ID},
        "suno.voice-validate": {"voice_url": AUDIO_URL, "vocal_start_s": 0, "vocal_end_s": 10},
        "suno.voice-regenerate": {"task_id": TASK_ID},
        "suno.voice-create": {"validation_task_id": TASK_ID, "verify_url": AUDIO_URL, "voice_name": "Smoke voice"},
    }
    if contract_id in suno:
        return suno[contract_id]

    midjourney: dict[str, dict[str, Any]] = {
        "midjourney.imagine": {"prompt": "A minimal white cube --ar 1:1 --v 8"},
        "midjourney.action": {"task_id": MJ_TASK_ID, "custom_id": MJ_CUSTOM_ID},
        "midjourney.change": {"task_id": MJ_TASK_ID, "action_type": "UPSCALE", "index": 1},
        "midjourney.blend": {"images": [IMAGE_URL, IMAGE_2_URL]},
        "midjourney.describe": {"image_url": IMAGE_URL},
        "midjourney.modal": {"task_id": MJ_TASK_ID, "prompt": "Replace the background"},
        "midjourney.editor": {"provider_payload": {"prompt": "Remove the object", "maskBase64": "${SMOKE_MASK_DATA_URL}"}},
        "midjourney.video": {"image_url": IMAGE_URL, "prompt": "gentle motion", "video_type": "vid_1.1_i2v_480"},
        "midjourney.fetch": {"task_id": MJ_TASK_ID},
        "midjourney.list": {"task_ids": [MJ_TASK_ID]},
    }
    if contract_id in midjourney:
        return midjourney[contract_id]

    llm_cases: dict[str, dict[str, Any]] = {
        "llm.kie.responses": {"messages": [{"role": "user", "content": "Reply with APIX smoke OK"}]},
        "llm.kie.claude": {"messages": [{"role": "user", "content": "Reply with APIX smoke OK"}]},
        "llm.comet.chat": {"messages": [{"role": "user", "content": "Reply with APIX smoke OK"}]},
        "llm.photo-prompt": {"image_base64": IMAGE_BASE64, "mime_type": "image/png"},
        "llm.moderation": {"prompt_text": "A harmless product photography prompt"},
    }
    if contract_id in llm_cases:
        return llm_cases[contract_id]

    raise KeyError(f"No smoke request template for {contract_id}")


SMOKE_CASES: dict[str, SmokeCase] = {
    contract.contract_id: SmokeCase(
        contract_id=contract.contract_id,
        params=_base_case(contract.contract_id),
    )
    for contract in ALL_CONTRACTS
}
