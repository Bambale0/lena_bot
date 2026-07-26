"""Backward-compatible Midjourney facade over the current Comet contract.

Existing Telegram and Mini App imports keep their public names while corrected
video payloads, provider statuses and newly documented operations are exposed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlencode

try:
    from enum import StrEnum
except ImportError:
    class StrEnum(str, Enum):
        pass
from typing import Any

import httpx

from api import comet_client
from api import midjourney_full_service as full
from core.config import settings

logger = logging.getLogger(__name__)


def _midjourney_notify_hook() -> str:
    base_url = settings.WEBHOOK_URL.rstrip("/")
    path = settings.MIDJOURNEY_WEBHOOK_PATH.strip()
    secret = (settings.MIDJOURNEY_WEBHOOK_SECRET or settings.WEBHOOK_SECRET).strip()
    if not base_url or not path:
        return ""
    url = f"{base_url}{path if path.startswith('/') else '/' + path}"
    if not secret:
        return url
    return f"{url}?{urlencode({'secret': secret})}"


class MJBotType(StrEnum):
    MIDJOURNEY = "MID_JOURNEY"
    NIJI = "NIJI_JOURNEY"

    def label(self) -> str:
        return {"MID_JOURNEY": "🎨 Midjourney", "NIJI_JOURNEY": "🌸 Niji Journey"}[self.value]


class MJSpeed(StrEnum):
    FAST = "FAST"
    RELAX = "RELAX"
    TURBO = "TURBO"

    def label(self) -> str:
        return {"FAST": "⚡ Fast", "RELAX": "😌 Relax", "TURBO": "🚀 Turbo"}[self.value]

    def path_prefix(self) -> str:
        return {"FAST": "/mj-fast", "RELAX": "", "TURBO": "/mj-turbo"}[self.value]


class MJTaskStatus(StrEnum):
    PENDING = "PENDING"
    NOT_START = "NOT_START"
    SUBMITTED = "SUBMITTED"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    CANCEL = "CANCEL"
    MODAL = "MODAL"

    @classmethod
    def terminal(cls) -> set["MJTaskStatus"]:
        return {cls.SUCCESS, cls.FAILURE, cls.CANCEL, cls.MODAL}


class MJDimensions(StrEnum):
    PORTRAIT = "PORTRAIT"
    SQUARE = "SQUARE"
    LANDSCAPE = "LANDSCAPE"


class MJVideoMotion(StrEnum):
    LOW = "low"
    HIGH = "high"

    def label(self) -> str:
        return {"low": "🐢 Low", "high": "🏎 High"}[self.value]


@dataclass
class MJButton:
    custom_id: str
    label: str
    emoji: str = ""
    btn_type: int = 2
    style: int = 1

    @property
    def display(self) -> str:
        return f"{self.emoji}{self.label}".strip()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MJButton":
        return cls(
            custom_id=str(payload.get("customId") or ""),
            label=str(payload.get("label") or ""),
            emoji=str(payload.get("emoji") or ""),
            btn_type=int(payload.get("type") or 2),
            style=int(payload.get("style") or 1),
        )


@dataclass
class MJTaskResult:
    task_id: str
    status: MJTaskStatus
    progress: str = ""
    image_url: str = ""
    image_urls: list[str] = field(default_factory=list)
    video_url: str = ""
    video_urls: list[str] = field(default_factory=list)
    prompt: str = ""
    fail_reason: str = ""
    buttons: list[MJButton] = field(default_factory=list)

    @property
    def is_done(self) -> bool:
        return self.status in MJTaskStatus.terminal()

    @property
    def is_success(self) -> bool:
        return self.status == MJTaskStatus.SUCCESS

    @property
    def needs_modal(self) -> bool:
        return self.status == MJTaskStatus.MODAL

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MJTaskResult":
        raw = str(payload.get("status") or "PENDING").upper()
        try:
            status = MJTaskStatus(raw)
        except ValueError:
            status = MJTaskStatus.PENDING
        properties = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
        prompt = str(
            payload.get("prompt")
            or payload.get("promptEn")
            or payload.get("prompt_en")
            or properties.get("finalPrompt")
            or properties.get("finalZhPrompt")
            or ""
        )
        return cls(
            task_id=str(payload.get("id") or payload.get("taskId") or ""),
            status=status,
            progress=str(payload.get("progress") or ""),
            image_url=str(payload.get("imageUrl") or ""),
            image_urls=[str(url) for url in (payload.get("image_urls") or []) if url],
            video_url=str(payload.get("videoUrl") or ""),
            video_urls=[str(url) for url in (payload.get("video_urls") or []) if url],
            prompt=prompt,
            fail_reason=str(payload.get("failReason") or ""),
            buttons=[
                MJButton.from_dict(item)
                for item in (payload.get("buttons") or [])
                if isinstance(item, dict) and item.get("customId")
            ],
        )


async def imagine(
    prompt: str,
    bot_type: MJBotType = MJBotType.MIDJOURNEY,
    speed: MJSpeed = MJSpeed.FAST,
    base64_array: list[str] | None = None,
    reference_url: str | None = None,
    state: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "botType": bot_type.value,
        "prompt": str(prompt).strip(),
        "accountFilter": {"modes": [speed.value]},
    }
    if not payload["prompt"]:
        raise ValueError("prompt is required")
    notify_hook = _midjourney_notify_hook()
    if notify_hook:
        payload["notifyHook"] = notify_hook
    if base64_array:
        payload["base64Array"] = list(base64_array)
    if state:
        payload["state"] = state
    try:
        response = await comet_client.post(f"{speed.path_prefix()}/mj/submit/imagine", payload)
    except httpx.HTTPStatusError as exc:
        retry_without_base64 = (
            bool(base64_array)
            and bool(reference_url)
            and exc.response is not None
            and exc.response.status_code in {400, 401, 403, 404, 422}
        )
        if not retry_without_base64:
            raise
        fallback_payload = dict(payload)
        fallback_payload.pop("base64Array", None)
        response = await comet_client.post(
            f"{speed.path_prefix()}/mj/submit/imagine",
            fallback_payload,
        )
    return full._task_id_from_response(response, "imagine")


async def fetch_task(task_id: str) -> MJTaskResult:
    response = await comet_client.get(f"/mj/task/{str(task_id).strip()}/fetch")
    if not isinstance(response, dict):
        raise RuntimeError(f"Midjourney fetch returned invalid payload: {response!r}")
    return MJTaskResult.from_dict(response)


async def action(
    task_id: str,
    custom_id: str,
    enable_remix: bool = False,
    state: str | None = None,
) -> str:
    return await full.action(
        task_id,
        custom_id,
        enable_remix=enable_remix,
        state=state,
    )


async def change(
    task_id: str,
    action_type: full.MidjourneyChangeAction | str,
    *,
    index: int | None = None,
    state: str | None = None,
) -> str:
    return await full.change(task_id, action_type, index=index, state=state)


async def modal(task_id: str, prompt: str = "", mask_base64: str = "") -> str:
    return await full.modal(task_id, prompt=prompt, mask_base64=mask_base64)


async def submit_editor(provider_payload: dict[str, Any]) -> str:
    return await full.submit_editor(provider_payload)


async def blend(
    base64_array: list[str],
    dimensions: MJDimensions = MJDimensions.SQUARE,
    bot_type: MJBotType = MJBotType.MIDJOURNEY,
) -> str:
    payload: dict[str, Any] = {
        "botType": bot_type.value,
        "base64Array": list(base64_array),
        "dimensions": dimensions.value,
    }
    notify_hook = _midjourney_notify_hook()
    if notify_hook:
        payload["notifyHook"] = notify_hook
    if not 2 <= len(base64_array) <= 5:
        raise ValueError("Midjourney blend requires 2-5 images")
    response = await comet_client.post("/mj/submit/blend", payload)
    return full._task_id_from_response(response, "blend")


async def describe(
    base64: str | None = None,
    link: str | None = None,
    bot_type: MJBotType = MJBotType.MIDJOURNEY,
) -> str:
    if bool(base64) == bool(link):
        raise ValueError("Provide exactly one of base64 or link")
    payload: dict[str, Any] = {"botType": bot_type.value}
    notify_hook = _midjourney_notify_hook()
    if notify_hook:
        payload["notifyHook"] = notify_hook
    if base64:
        payload["base64"] = base64
    else:
        payload["link"] = link
    response = await comet_client.post("/mj/submit/describe", payload)
    return full._task_id_from_response(response, "describe")


async def submit_video(
    image: str,
    motion: MJVideoMotion = MJVideoMotion.LOW,
    prompt: str = "",
    video_type: str = "vid_1.1_i2v_480",
) -> str:
    return await full.submit_video(
        image,
        prompt=prompt,
        video_type=video_type,
        mode=full.MidjourneyVideoMode.FAST,
        animate_mode=full.MidjourneyAnimateMode.MANUAL,
        motion=full.MidjourneyMotion(motion.value),
    )


async def list_by_condition(task_ids: list[str]) -> list[MJTaskResult]:
    response = await comet_client.post("/mj/task/list-by-condition", {"ids": task_ids})
    if isinstance(response, dict):
        response = response.get("data") or response.get("result") or []
    if not isinstance(response, list):
        return []
    return [MJTaskResult.from_dict(item) for item in response if isinstance(item, dict)]


async def poll_mj_image(task_id: str) -> str | None:
    result = await fetch_task(task_id)
    if result.status == MJTaskStatus.SUCCESS:
        return result.image_url or (result.image_urls[0] if result.image_urls else "done")
    if result.status in {MJTaskStatus.FAILURE, MJTaskStatus.CANCEL}:
        raise RuntimeError(result.fail_reason or "Midjourney task failed")
    if result.status == MJTaskStatus.MODAL:
        raise RuntimeError("__MODAL__")
    return None


async def poll_mj_video(task_id: str) -> str | None:
    result = await fetch_task(task_id)
    if result.status == MJTaskStatus.SUCCESS:
        if result.video_urls:
            return result.video_urls[0]
        if result.video_url:
            return result.video_url
        raise RuntimeError("Midjourney video task succeeded without video URL")
    if result.status in {MJTaskStatus.FAILURE, MJTaskStatus.CANCEL}:
        raise RuntimeError(result.fail_reason or "Midjourney video task failed")
    return None
