# api/midjourney_service.py
"""
Midjourney через CometAPI — полный набор операций.

Workflow:
  imagine  → webhook/fetch → action → fetch (poll) [→ modal → fetch]
  blend    → webhook/fetch
  describe → webhook/fetch
  video    → webhook/fetch
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


# ── Enums ─────────────────────────────────────────────────────────────────────

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
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    MODAL = "MODAL"

    @classmethod
    def terminal(cls) -> set["MJTaskStatus"]:
        return {cls.SUCCESS, cls.FAILURE, cls.MODAL}


class MJDimensions(StrEnum):
    PORTRAIT = "PORTRAIT"
    SQUARE = "SQUARE"
    LANDSCAPE = "LANDSCAPE"


class MJVideoMotion(StrEnum):
    LOW = "low"
    HIGH = "high"

    def label(self) -> str:
        return {"low": "🐢 Low", "high": "🏎 High"}[self.value]


# ── Data classes ──────────────────────────────────────────────────────────────

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
    def from_dict(cls, d: dict[str, Any]) -> "MJButton":
        return cls(
            custom_id=d.get("customId", ""),
            label=d.get("label", ""),
            emoji=d.get("emoji", ""),
            btn_type=d.get("type", 2),
            style=d.get("style", 1),
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
    def from_dict(cls, d: dict[str, Any]) -> "MJTaskResult":
        raw_status = str(d.get("status") or "").strip().upper()
        if raw_status not in MJTaskStatus._value2member_map_:
            if raw_status:
                logger.warning("Unknown MJ task status %r for task %s; fallback to PENDING", raw_status, d.get("id", ""))
            raw_status = MJTaskStatus.PENDING
        raw_buttons = d.get("buttons") or []
        return cls(
            task_id=str(d.get("id", "")),
            status=MJTaskStatus(raw_status),
            progress=d.get("progress", ""),
            image_url=d.get("imageUrl", ""),
            image_urls=[url for url in (d.get("image_urls") or []) if isinstance(url, str) and url],
            video_url=d.get("videoUrl", ""),
            video_urls=[url for url in (d.get("video_urls") or []) if isinstance(url, str) and url],
            prompt=d.get("prompt", ""),
            fail_reason=d.get("failReason", ""),
            buttons=[MJButton.from_dict(b) for b in raw_buttons if isinstance(b, dict) and b.get("customId")],
        )


# ── Core API calls ────────────────────────────────────────────────────────────

async def imagine(
    prompt: str,
    bot_type: MJBotType = MJBotType.MIDJOURNEY,
    speed: MJSpeed = MJSpeed.FAST,
    base64_array: list[str] | None = None,
    reference_url: str | None = None,
    state: str | None = None,
) -> str:
    """Submit imagine task. Returns task_id."""
    prefix = speed.path_prefix()
    payload: dict[str, Any] = {
        "botType": bot_type.value,
        "prompt": prompt,
        "accountFilter": {"modes": [speed.value]},
    }
    notify_hook = _midjourney_notify_hook()
    if notify_hook:
        payload["notifyHook"] = notify_hook
    if base64_array:
        payload["base64Array"] = base64_array
    if state:
        payload["state"] = state

    try:
        resp = await comet_client.post(f"{prefix}/mj/submit/imagine", payload)
    except httpx.HTTPStatusError as exc:
        should_retry_without_base64 = (
            bool(base64_array)
            and bool(reference_url)
            and exc.response.status_code in {400, 401, 403, 404, 422}
        )
        if not should_retry_without_base64:
            raise

        fallback_payload = dict(payload)
        fallback_payload.pop("base64Array", None)
        logger.warning(
            "MJ imagine rejected image reference payload, retrying with URL-only prompt: status=%s reference_url=%s",
            exc.response.status_code,
            reference_url,
        )
        resp = await comet_client.post(f"{prefix}/mj/submit/imagine", fallback_payload)

    task_id = str(resp["result"])
    logger.info("MJ imagine submitted: task_id=%s, prompt=%.60s", task_id, prompt)
    return task_id


async def fetch_task(task_id: str) -> MJTaskResult:
    """Poll single task status."""
    resp = await comet_client.get(f"/mj/task/{task_id}/fetch")
    return MJTaskResult.from_dict(resp)


async def action(
    task_id: str,
    custom_id: str,
    enable_remix: bool = False,
    state: str | None = None,
) -> str:
    """Submit action (upscale / variation / zoom / pan / reroll). Returns new task_id."""
    payload: dict[str, Any] = {
        "taskId": task_id,
        "customId": custom_id,
        "enableRemix": enable_remix,
    }
    if state:
        payload["state"] = state

    resp = await comet_client.post("/mj/submit/action", payload)
    new_task_id = str(resp["result"])
    logger.info("MJ action submitted: parent=%s → new=%s, customId=%.40s", task_id, new_task_id, custom_id)
    return new_task_id


async def modal(
    task_id: str,
    prompt: str = "",
    mask_base64: str = "",
) -> str:
    """Submit modal input (Vary Region / Custom Zoom). Returns new task_id."""
    payload: dict[str, Any] = {"taskId": task_id}
    if prompt:
        payload["prompt"] = prompt
    if mask_base64:
        payload["maskBase64"] = mask_base64

    resp = await comet_client.post("/mj/submit/modal", payload)
    new_task_id = str(resp["result"])
    logger.info("MJ modal submitted: parent=%s → new=%s", task_id, new_task_id)
    return new_task_id


async def blend(
    base64_array: list[str],
    dimensions: MJDimensions = MJDimensions.SQUARE,
    bot_type: MJBotType = MJBotType.MIDJOURNEY,
) -> str:
    """Blend 2–5 images. Returns task_id."""
    payload: dict[str, Any] = {
        "botType": bot_type.value,
        "base64Array": base64_array,
        "dimensions": dimensions.value,
    }
    notify_hook = _midjourney_notify_hook()
    if notify_hook:
        payload["notifyHook"] = notify_hook
    resp = await comet_client.post("/mj/submit/blend", payload)
    task_id = str(resp["result"])
    logger.info("MJ blend submitted: task_id=%s, images=%d", task_id, len(base64_array))
    return task_id


async def describe(
    base64: str | None = None,
    link: str | None = None,
    bot_type: MJBotType = MJBotType.MIDJOURNEY,
) -> str:
    """Describe image → get prompt candidates. Returns task_id."""
    payload: dict[str, Any] = {"botType": bot_type.value}
    notify_hook = _midjourney_notify_hook()
    if notify_hook:
        payload["notifyHook"] = notify_hook
    if base64:
        payload["base64"] = base64
    elif link:
        payload["link"] = link
    else:
        raise ValueError("Нужен base64 или link")

    resp = await comet_client.post("/mj/submit/describe", payload)
    task_id = str(resp["result"])
    logger.info("MJ describe submitted: task_id=%s", task_id)
    return task_id


async def submit_video(
    image: str,
    motion: MJVideoMotion = MJVideoMotion.LOW,
    prompt: str = "",
    video_type: str = "vid_1.1_i2v_720",
) -> str:
    """Convert image to video. Returns task_id."""
    payload: dict[str, Any] = {
        "image": image,
        "motion": motion.value,
        "videoType": video_type,
    }
    notify_hook = _midjourney_notify_hook()
    if notify_hook:
        payload["notifyHook"] = notify_hook
    if prompt:
        payload["prompt"] = prompt

    resp = await comet_client.post("/mj/submit/video", payload)
    task_id = str(resp["result"])
    logger.info("MJ video submitted: task_id=%s", task_id)
    return task_id


async def list_by_condition(task_ids: list[str]) -> list[MJTaskResult]:
    """Batch status check by list of task IDs."""
    resp_list = await comet_client.post("/mj/task/list-by-condition", {"ids": task_ids})
    if not isinstance(resp_list, list):
        return []
    return [MJTaskResult.from_dict(item) for item in resp_list]


# ── Polling helpers ───────────────────────────────────────────────────────────

async def poll_mj_image(task_id: str) -> str | None:
    """
    Совместим с api.polling.poll_until_done.
    Возвращает imageUrl при SUCCESS, None если ещё идёт,
    при FAILURE/MODAL — бросает RuntimeError.
    """
    result = await fetch_task(task_id)
    if result.status == MJTaskStatus.SUCCESS:
        return result.image_url or "done"
    if result.status == MJTaskStatus.FAILURE:
        raise RuntimeError(result.fail_reason or "Midjourney task failed")
    if result.status == MJTaskStatus.MODAL:
        raise RuntimeError("__MODAL__")  # обработчик поймает и перейдёт в waiting_modal
    return None  # ещё в процессе


async def poll_mj_video(task_id: str) -> str | None:
    """Polling для видео-задачи MJ."""
    result = await fetch_task(task_id)
    if result.status == MJTaskStatus.SUCCESS:
        return result.video_url or (result.video_urls[0] if result.video_urls else "") or result.image_url or "done"
    if result.status == MJTaskStatus.FAILURE:
        raise RuntimeError(result.fail_reason or "MJ video task failed")
    return None
