"""Machine-readable provider contract inventory for APIX.

Every model and credit-consuming provider operation must appear here with an
official documentation reference, implementation entrypoint, contract tests and
product exposure. The coverage script compares this catalog with runtime enums
and provider registries to prevent silent capability drift.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

DOCS_VERIFIED_ON = "2026-07-26"


@dataclass(frozen=True)
class ProviderContract:
    contract_id: str
    provider: str
    model: str
    modes: tuple[str, ...]
    official_docs: tuple[str, ...]
    backend_entrypoints: tuple[str, ...]
    contract_tests: tuple[str, ...]
    billing: bool = True
    telegram: bool = False
    miniapp: bool = False
    public_api: bool = False
    live_smoke_id: str | None = None
    notes: str = ""
    docs_verified_on: str = DOCS_VERIFIED_ON

    @property
    def has_user_surface(self) -> bool:
        return self.telegram or self.miniapp or self.public_api

    @property
    def contract_valid(self) -> bool:
        return bool(
            self.contract_id
            and self.provider
            and self.model
            and self.modes
            and self.official_docs
            and self.backend_entrypoints
            and self.contract_tests
            and self.docs_verified_on
        )

    @property
    def product_ready(self) -> bool:
        return bool(
            self.contract_valid
            and self.billing
            and self.has_user_surface
            and self.live_smoke_id
        )


def _c(
    contract_id: str,
    provider: str,
    model: str,
    modes: Iterable[str],
    docs: Iterable[str],
    backend: Iterable[str],
    tests: Iterable[str],
    *,
    billing: bool = True,
    telegram: bool = False,
    miniapp: bool = False,
    public_api: bool = False,
    smoke: str | None = None,
    notes: str = "",
) -> ProviderContract:
    return ProviderContract(
        contract_id=contract_id,
        provider=provider,
        model=model,
        modes=tuple(modes),
        official_docs=tuple(docs),
        backend_entrypoints=tuple(backend),
        contract_tests=tuple(tests),
        billing=billing,
        telegram=telegram,
        miniapp=miniapp,
        public_api=public_api,
        live_smoke_id=smoke,
        notes=notes,
    )


_IMAGE_BACKEND = ("api.image_service:generate_image",)
_IMAGE_TEST = ("tests/test_image_provider_contracts.py",)
_IMAGE_SURFACES = {"telegram": True, "miniapp": True}

IMAGE_CONTRACTS = (
    _c("image.seedream5.t2i", "kie", "seedream/5-pro-text-to-image", ("text",), ("https://docs.kie.ai/market/seedream/5-pro-text-to-image",), _IMAGE_BACKEND, _IMAGE_TEST, smoke="image.seedream5.t2i", **_IMAGE_SURFACES),
    _c("image.seedream5.i2i", "kie", "seedream/5-pro-image-to-image", ("image",), ("https://docs.kie.ai/market/seedream/5-pro-image-to-image",), _IMAGE_BACKEND, _IMAGE_TEST, smoke="image.seedream5.i2i", **_IMAGE_SURFACES),
    _c("image.seedream45.t2i", "kie", "seedream/4.5-text-to-image", ("text",), ("https://docs.kie.ai/market/seedream/4-5-text-to-image",), _IMAGE_BACKEND, _IMAGE_TEST, smoke="image.seedream45.t2i", **_IMAGE_SURFACES),
    _c("image.seedream45.edit", "kie", "seedream/4.5-edit", ("image",), ("https://docs.kie.ai/market/seedream/4-5-edit",), _IMAGE_BACKEND, _IMAGE_TEST, smoke="image.seedream45.edit", **_IMAGE_SURFACES),
    _c("image.grok.t2i", "kie", "grok-imagine/text-to-image", ("text",), ("https://docs.kie.ai/market/grok-imagine/text-to-image",), _IMAGE_BACKEND, _IMAGE_TEST, smoke="image.grok.t2i", **_IMAGE_SURFACES),
    _c("image.grok.i2i", "kie", "grok-imagine/image-to-image", ("image",), ("https://docs.kie.ai/market/grok-imagine/image-to-image",), _IMAGE_BACKEND, _IMAGE_TEST, smoke="image.grok.i2i", **_IMAGE_SURFACES),
    _c("image.wan27", "kie", "wan/2-7-image", ("text", "image"), ("https://docs.kie.ai/market/wan/2-7-image",), _IMAGE_BACKEND, _IMAGE_TEST, smoke="image.wan27", **_IMAGE_SURFACES),
    _c("image.wan27.pro", "kie", "wan/2-7-image-pro", ("text", "image"), ("https://docs.kie.ai/market/wan/2-7-image-pro",), _IMAGE_BACKEND, _IMAGE_TEST, smoke="image.wan27.pro", **_IMAGE_SURFACES),
    _c("image.nano.legacy", "kie", "google/nano-banana", ("text",), ("https://docs.kie.ai/market/google/nano-banana",), _IMAGE_BACKEND, _IMAGE_TEST, smoke="image.nano.legacy", **_IMAGE_SURFACES),
    _c("image.nano2", "comet", "nano-banana-2", ("text", "image"), ("https://ai.google.dev/gemini-api/docs/image-generation",), _IMAGE_BACKEND, ("tests/test_image_service.py",), smoke="image.nano2", **_IMAGE_SURFACES),
    _c("image.nano2.lite", "kie", "nano-banana-2-lite", ("text", "image"), ("https://docs.kie.ai/market/google/nano-banana-2-lite",), _IMAGE_BACKEND, _IMAGE_TEST, smoke="image.nano2.lite", **_IMAGE_SURFACES),
    _c("image.nano.pro", "comet", "nano-banana-pro", ("text", "image"), ("https://ai.google.dev/gemini-api/docs/image-generation",), _IMAGE_BACKEND, ("tests/test_image_service.py",), smoke="image.nano.pro", **_IMAGE_SURFACES),
    _c("image.qwen.t2i", "kie", "qwen/text-to-image", ("text",), ("https://docs.kie.ai/market/qwen/text-to-image",), _IMAGE_BACKEND, _IMAGE_TEST, smoke="image.qwen.t2i", **_IMAGE_SURFACES),
    _c("image.qwen.i2i", "kie", "qwen/image-to-image", ("image",), ("https://docs.kie.ai/market/qwen/image-to-image",), _IMAGE_BACKEND, _IMAGE_TEST, smoke="image.qwen.i2i", **_IMAGE_SURFACES),
    _c("image.qwen.edit", "kie", "qwen/image-edit", ("image",), ("https://docs.kie.ai/market/qwen/image-edit",), _IMAGE_BACKEND, _IMAGE_TEST, smoke="image.qwen.edit", **_IMAGE_SURFACES),
    _c("image.qwen2.t2i", "kie", "qwen2/text-to-image", ("text",), ("https://docs.kie.ai/market/qwen2/text-to-image",), _IMAGE_BACKEND, _IMAGE_TEST, smoke="image.qwen2.t2i", **_IMAGE_SURFACES),
    _c("image.qwen2.edit", "kie", "qwen2/image-edit", ("image",), ("https://docs.kie.ai/market/qwen2/image-edit",), _IMAGE_BACKEND, _IMAGE_TEST, smoke="image.qwen2.edit", **_IMAGE_SURFACES),
    _c("image.gpt2.t2i", "kie", "gpt-image-2-text-to-image", ("text",), ("https://docs.kie.ai/market/gpt/gpt-image-2-text-to-image",), _IMAGE_BACKEND, ("tests/test_gpt_image_2_references.py",), smoke="image.gpt2.t2i", **_IMAGE_SURFACES),
    _c("image.gpt2.i2i", "kie", "gpt-image-2-image-to-image", ("image",), ("https://docs.kie.ai/market/gpt/gpt-image-2-image-to-image",), _IMAGE_BACKEND, ("tests/test_gpt_image_2_references.py",), smoke="image.gpt2.i2i", **_IMAGE_SURFACES),
)


_VIDEO_BACKEND = ("api.video_service:generate_video",)
_VIDEO_TEST = ("tests/test_provider_spec_p0.py",)
_VIDEO_SURFACES = {"telegram": True, "miniapp": True}

VIDEO_CONTRACTS = (
    _c("video.kling26.t2v", "kie", "kling-2.6/text-to-video", ("text",), ("https://docs.kie.ai/market/kling/text-to-video",), _VIDEO_BACKEND, _VIDEO_TEST, smoke="video.kling26.t2v", **_VIDEO_SURFACES),
    _c("video.kling26.i2v", "kie", "kling-2.6/image-to-video", ("image",), ("https://docs.kie.ai/market/kling/image-to-video",), _VIDEO_BACKEND, _VIDEO_TEST, smoke="video.kling26.i2v", **_VIDEO_SURFACES),
    _c("video.kling26.motion", "kie", "kling-2.6/motion-control", ("motion",), ("https://docs.kie.ai/market/kling/motion-control",), ("api.kling_grok_service:create_kling_motion_control",), ("tests/test_kling_grok_service.py",), smoke="video.kling26.motion", **_VIDEO_SURFACES),
    _c("video.kling30", "kie", "kling-3.0/video", ("text", "image", "multi_shot", "elements"), ("https://docs.kie.ai/market/kling/kling-3-0",), ("api.kling_grok_service:create_kling_30_video",), ("tests/test_kling_grok_service.py",), smoke="video.kling30", **_VIDEO_SURFACES),
    _c("video.kling30.motion", "kie", "kling-3.0/motion-control", ("motion",), ("https://docs.kie.ai/market/kling/motion-control-v3",), ("api.kling_grok_service:create_kling_motion_control",), ("tests/test_kling_grok_service.py",), smoke="video.kling30.motion", **_VIDEO_SURFACES),
    _c("video.klingv3.turbo.t2v", "kie", "kling/v3-turbo-text-to-video", ("text",), ("https://docs.kie.ai/market/kling/v3-turbo-text-to-video",), ("api.kling_grok_service:create_kling_v3_turbo_text",), ("tests/test_kling_grok_service.py",), smoke="video.klingv3.turbo.t2v", **_VIDEO_SURFACES),
    _c("video.klingv3.turbo.i2v", "kie", "kling/v3-turbo-image-to-video", ("image",), ("https://docs.kie.ai/market/kling/v3-turbo-image-to-video",), ("api.kling_grok_service:create_kling_v3_turbo_image",), ("tests/test_kling_grok_service.py",), smoke="video.klingv3.turbo.i2v", **_VIDEO_SURFACES),
    _c("video.wan27.t2v", "kie", "wan/2-7-text-to-video", ("text", "audio"), ("https://docs.kie.ai/market/wan/2-7-text-to-video",), ("api.advanced_video_service:create_wan_text_to_video",), ("tests/test_advanced_video_service.py",), smoke="video.wan27.t2v", **_VIDEO_SURFACES),
    _c("video.wan27.i2v", "kie", "wan/2-7-image-to-video", ("first_frame", "first_last", "continue"), ("https://docs.kie.ai/market/wan/2-7-image-to-video",), ("api.advanced_video_service:create_wan_image_to_video",), ("tests/test_advanced_video_service.py",), smoke="video.wan27.i2v", **_VIDEO_SURFACES),
    _c("video.seedance2", "kie", "bytedance/seedance-2", ("text", "frame", "multimodal"), ("https://docs.kie.ai/market/bytedance/seedance-2",), ("api.advanced_video_service:create_seedance_task",), ("tests/test_advanced_video_service.py",), smoke="video.seedance2", **_VIDEO_SURFACES),
    _c("video.seedance2.fast", "kie", "bytedance/seedance-2-fast", ("text", "frame", "multimodal"), ("https://docs.kie.ai/market/bytedance/seedance-2-fast",), ("api.advanced_video_service:create_seedance_task",), ("tests/test_advanced_video_service.py",), smoke="video.seedance2.fast", **_VIDEO_SURFACES),
    _c("video.seedance2.mini", "kie", "bytedance/seedance-2-mini", ("text", "frame", "multimodal"), ("https://docs.kie.ai/market/bytedance/seedance-2-mini",), ("api.advanced_video_service:create_seedance_task",), ("tests/test_advanced_video_service.py",), smoke="video.seedance2.mini", **_VIDEO_SURFACES),
    _c("video.seedance25", "kie", "bytedance/seedance-2-5", ("text", "first_frame", "first_last", "multimodal", "audio"), ("https://docs.kie.ai/market/bytedance/seedance-2-5",), _VIDEO_BACKEND, ("tests/test_seedance25_admin_model_visibility.py",), smoke="video.seedance25", **_VIDEO_SURFACES),
    _c("video.grok.t2v", "kie", "grok-imagine/text-to-video", ("text",), ("https://docs.kie.ai/market/grok-imagine/text-to-video",), _VIDEO_BACKEND, _VIDEO_TEST, smoke="video.grok.t2v", **_VIDEO_SURFACES),
    _c("video.grok.i2v", "kie", "grok-imagine/image-to-video", ("source_task", "image"), ("https://docs.kie.ai/market/grok-imagine/image-to-video",), _VIDEO_BACKEND, _VIDEO_TEST, smoke="video.grok.i2v", **_VIDEO_SURFACES),
    _c("video.happyhorse.t2v", "kie", "happyhorse/text-to-video", ("text",), ("https://docs.kie.ai/market/happyhorse/text-to-video",), ("api.advanced_video_service:create_happyhorse_text_to_video",), ("tests/test_advanced_video_service.py",), smoke="video.happyhorse.t2v", **_VIDEO_SURFACES),
    _c("video.happyhorse.i2v", "kie", "happyhorse/image-to-video", ("image",), ("https://docs.kie.ai/market/happyhorse/image-to-video",), ("api.advanced_video_service:create_happyhorse_image_to_video",), ("tests/test_advanced_video_service.py",), smoke="video.happyhorse.i2v", **_VIDEO_SURFACES),
    _c("video.gemini.omni", "kie", "gemini-omni-video", ("text", "image", "video", "audio_id", "character_id"), ("https://docs.kie.ai/market/gemini-omni-video",), _VIDEO_BACKEND, _VIDEO_TEST, smoke="video.gemini.omni", **_VIDEO_SURFACES),
    _c("video.veo3", "kie", "veo3", ("text", "first_last"), ("https://docs.kie.ai/veo3-api/generate-veo-3-video",), _VIDEO_BACKEND, ("tests/test_provider_spec_p0.py", "tests/test_veo_capabilities.py"), smoke="video.veo3", **_VIDEO_SURFACES),
    _c("video.veo3.fast", "kie", "veo3_fast", ("text", "first_last", "reference"), ("https://docs.kie.ai/veo3-api/generate-veo-3-video",), _VIDEO_BACKEND, ("tests/test_provider_spec_p0.py", "tests/test_veo_capabilities.py"), smoke="video.veo3.fast", **_VIDEO_SURFACES),
    _c("video.veo3.lite", "kie", "veo3_lite", ("text", "first_last", "reference"), ("https://docs.kie.ai/veo3-api/generate-veo-3-video",), _VIDEO_BACKEND, ("tests/test_provider_spec_p0.py", "tests/test_veo_capabilities.py"), smoke="video.veo3.lite", **_VIDEO_SURFACES),
)


_ADVANCED_TEST = ("tests/test_advanced_video_service.py",)
ADVANCED_VIDEO_CONTRACTS = (
    _c("video.wan27.r2v", "kie", "wan/2-7-r2v", ("reference",), ("https://docs.kie.ai/market/wan/2-7-r2v",), ("api.advanced_video_service:create_wan_reference_to_video",), _ADVANCED_TEST, public_api=False, smoke="video.wan27.r2v"),
    _c("video.wan27.edit", "kie", "wan/2-7-videoedit", ("video_edit",), ("https://docs.kie.ai/market/wan/2-7-video-edit",), ("api.advanced_video_service:create_wan_video_edit",), _ADVANCED_TEST, public_api=False, smoke="video.wan27.edit"),
    _c("video.happyhorse.r2v", "kie", "happyhorse/reference-to-video", ("reference",), ("https://docs.kie.ai/market/happyhorse/reference-to-video",), ("api.advanced_video_service:create_happyhorse_reference_to_video",), _ADVANCED_TEST, public_api=False, smoke="video.happyhorse.r2v"),
    _c("video.happyhorse.edit", "kie", "happyhorse/video-edit", ("video_edit",), ("https://docs.kie.ai/market/happyhorse/video-edit",), ("api.advanced_video_service:create_happyhorse_video_edit",), _ADVANCED_TEST, public_api=False, smoke="video.happyhorse.edit"),
    _c("video.happyhorse11.t2v", "kie", "happyhorse-1-1/text-to-video", ("text",), ("https://docs.kie.ai/market/happyhorse-1-1/text-to-video",), ("api.advanced_video_service:create_happyhorse_text_to_video",), _ADVANCED_TEST, public_api=False, smoke="video.happyhorse11.t2v"),
    _c("video.happyhorse11.i2v", "kie", "happyhorse-1-1/image-to-video", ("image",), ("https://docs.kie.ai/market/happyhorse-1-1/image-to-video",), ("api.advanced_video_service:create_happyhorse_image_to_video",), _ADVANCED_TEST, public_api=False, smoke="video.happyhorse11.i2v"),
    _c("video.happyhorse11.r2v", "kie", "happyhorse-1-1/reference-to-video", ("reference",), ("https://docs.kie.ai/market/happyhorse-1-1/reference-to-video",), ("api.advanced_video_service:create_happyhorse_reference_to_video",), _ADVANCED_TEST, public_api=False, smoke="video.happyhorse11.r2v"),
    _c("video.grok.upscale", "kie", "grok-imagine/upscale", ("upscale",), ("https://docs.kie.ai/market/grok-imagine/upscale",), ("api.kling_grok_service:create_grok_upscale",), ("tests/test_kling_grok_service.py",), public_api=False, smoke="video.grok.upscale"),
    _c("video.grok.extend", "kie", "grok-imagine/extend", ("extend",), ("https://docs.kie.ai/market/grok-imagine/extend",), ("api.kling_grok_service:create_grok_extend",), ("tests/test_kling_grok_service.py",), public_api=False, smoke="video.grok.extend"),
    _c("video.grok.preview15", "kie", "grok-imagine-video-1-5-preview", ("text", "image"), ("https://docs.kie.ai/market/grok-imagine/video-1-5-preview",), ("api.kling_grok_service:create_grok_preview_15",), ("tests/test_kling_grok_service.py",), public_api=False, smoke="video.grok.preview15"),
    _c("video.veo.extend", "kie", "veo/extend", ("extend",), ("https://docs.kie.ai/veo3-api/extend-video",), ("api.video_service:extend_veo_video",), _VIDEO_TEST, public_api=False, smoke="video.veo.extend"),
    _c("video.veo.1080", "kie", "veo/get-1080p-video", ("enhance",), ("https://docs.kie.ai/veo3-api/get-1080p-video",), ("api.video_service:get_veo_1080p_url",), _VIDEO_TEST, public_api=False, smoke="video.veo.1080"),
    _c("video.veo.4k", "kie", "veo/get-4k-video", ("enhance",), ("https://docs.kie.ai/veo3-api/get-4k-video",), ("api.video_service:generate_video_4k",), _VIDEO_TEST, public_api=False, smoke="video.veo.4k"),
)


SUNO_OPERATIONS = {
    "generate": "generate_music",
    "extend": "extend_music",
    "upload-cover": "upload_and_cover",
    "upload-extend": "upload_and_extend",
    "add-instrumental": "add_instrumental",
    "add-vocals": "add_vocals",
    "replace-section": "replace_section",
    "persona": "generate_persona",
    "mashup": "generate_mashup",
    "lyrics": "generate_lyrics",
    "timestamped-lyrics": "get_timestamped_lyrics",
    "style": "boost_style",
    "cover-art": "generate_cover_art",
    "wav": "convert_to_wav",
    "stems": "separate_stems",
    "midi": "generate_midi",
    "music-video": "create_music_video",
    "voice-validate": "create_voice_validation",
    "voice-regenerate": "regenerate_voice_validation",
    "voice-create": "create_custom_voice",
}
SUNO_CONTRACTS = tuple(
    _c(
        f"suno.{operation}",
        "kie",
        f"suno/{operation}",
        (operation,),
        ("https://docs.kie.ai/suno-api",),
        (f"api.suno_full_service:{function}",),
        ("tests/test_suno_full_service.py",),
        public_api=False,
        smoke=f"suno.{operation}",
    )
    for operation, function in SUNO_OPERATIONS.items()
)


MIDJOURNEY_OPERATIONS = {
    "imagine": "imagine",
    "action": "action",
    "change": "change",
    "blend": "blend",
    "describe": "describe",
    "modal": "modal",
    "editor": "submit_editor",
    "video": "submit_video",
    "fetch": "fetch_task",
    "list": "list_by_condition",
}
MIDJOURNEY_CONTRACTS = tuple(
    _c(
        f"midjourney.{operation}",
        "comet",
        f"midjourney/{operation}",
        (operation,),
        ("https://www.cometapi.com/models/midjourney",),
        (f"api.midjourney_full_service:{function}",),
        ("tests/test_midjourney_full_service.py",),
        billing=operation not in {"fetch", "list"},
        telegram=operation in {"imagine", "action", "blend", "describe", "modal", "video"},
        miniapp=operation in {"imagine", "action", "blend", "describe", "video"},
        public_api=False,
        smoke=f"midjourney.{operation}" if operation not in {"fetch", "list"} else None,
    )
    for operation, function in MIDJOURNEY_OPERATIONS.items()
)


LLM_CONTRACTS = (
    _c("llm.kie.responses", "kie", "gpt-responses", ("text", "vision", "tools", "web_search"), ("https://docs.kie.ai/market/chat/gpt-5-5",), ("api.llm_provider_service:call_route",), ("tests/test_llm_provider_contracts.py",), billing=False, public_api=False, smoke="llm.kie.responses"),
    _c("llm.kie.claude", "kie", "claude-sonnet-4-5", ("text", "tools", "thinking"), ("https://docs.kie.ai/market/chat/claude-sonnet-4-5",), ("api.llm_provider_service:call_route",), ("tests/test_llm_provider_contracts.py",), billing=False, public_api=False, smoke="llm.kie.claude"),
    _c("llm.comet.chat", "comet", "openai-compatible-chat", ("text", "vision", "tools", "json_schema"), ("https://www.cometapi.com/docs",), ("api.llm_provider_service:call_route",), ("tests/test_llm_provider_contracts.py",), billing=False, public_api=False, smoke="llm.comet.chat"),
    _c("llm.photo-prompt", "kie+comet", "photo-prompt-router", ("vision",), ("https://docs.kie.ai/market/chat/gpt-5-2",), ("api.photo_prompt_service:generate_prompt_from_photo_result",), ("tests/test_photo_prompt_service.py", "tests/test_llm_provider_contracts.py"), billing=False, telegram=True, miniapp=True, smoke="llm.photo-prompt"),
    _c("llm.moderation", "comet", "strict-json-moderation", ("json_schema",), ("https://platform.openai.com/docs/guides/structured-outputs",), ("api.assistant_service:generate_prompt_moderation_decision",), ("tests/test_llm_provider_contracts.py", "tests/test_moderation_review_contract.py"), billing=False, telegram=True, miniapp=True, smoke="llm.moderation"),
)


ALL_CONTRACTS: tuple[ProviderContract, ...] = (
    *IMAGE_CONTRACTS,
    *VIDEO_CONTRACTS,
    *ADVANCED_VIDEO_CONTRACTS,
    *SUNO_CONTRACTS,
    *MIDJOURNEY_CONTRACTS,
    *LLM_CONTRACTS,
)
CONTRACTS_BY_ID = {contract.contract_id: contract for contract in ALL_CONTRACTS}
CONTRACTS_BY_MODEL = {contract.model: contract for contract in ALL_CONTRACTS}
