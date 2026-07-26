"""Complete documented Midjourney surface for CometAPI.

Current Comet documentation lists Imagine, Action/Change, Blend, Describe,
Modal, Editor, Video, single-task fetch and list-by-condition. Unsupported or
undocumented utility endpoints are deliberately not invented here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from api import comet_client


class MidjourneyBot(StrEnum):
    MIDJOURNEY = "MID_JOURNEY"
    NIJI = "NIJI_JOURNEY"


class MidjourneySpeed(StrEnum):
    RELAX = "RELAX"
    FAST = "FAST"
    TURBO = "TURBO"

    @property
    def route_prefix(self) -> str:
        return {
            MidjourneySpeed.RELAX: "",
            MidjourneySpeed.FAST: "/mj-fast",
            MidjourneySpeed.TURBO: "/mj-turbo",
        }[self]


class BlendDimensions(StrEnum):
    PORTRAIT = "PORTRAIT"
    SQUARE = "SQUARE"
    LANDSCAPE = "LANDSCAPE"


class MidjourneyChangeAction(StrEnum):
    UPSCALE = "UPSCALE"
    VARIATION = "VARIATION"
    REROLL = "REROLL"


class MidjourneyMotion(StrEnum):
    LOW = "low"
    HIGH = "high"


class MidjourneyVideoMode(StrEnum):
    RELAX = "relax"
    FAST = "fast"
    TURBO = "turbo"


class MidjourneyAnimateMode(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class MidjourneyTaskStatus(StrEnum):
    NOT_START = "NOT_START"
    SUBMITTED = "SUBMITTED"
    MODAL = "MODAL"
    IN_PROGRESS = "IN_PROGRESS"
    FAILURE = "FAILURE"
    SUCCESS = "SUCCESS"
    CANCEL = "CANCEL"

    @property
    def terminal(self) -> bool:
        return self in {
            MidjourneyTaskStatus.FAILURE,
            MidjourneyTaskStatus.SUCCESS,
            MidjourneyTaskStatus.CANCEL,
        }


@dataclass(frozen=True)
class MidjourneyButton:
    custom_id: str
    label: str = ""
    emoji: str = ""
    type: int = 2
    style: int = 1

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MidjourneyButton":
        return cls(
            custom_id=str(payload.get("customId") or ""),
            label=str(payload.get("label") or ""),
            emoji=str(payload.get("emoji") or ""),
            type=int(payload.get("type") or 2),
            style=int(payload.get("style") or 1),
        )


@dataclass(frozen=True)
class MidjourneyTask:
    task_id: str
    action: str = ""
    status: MidjourneyTaskStatus = MidjourneyTaskStatus.NOT_START
    progress: str = ""
    prompt: str = ""
    image_url: str = ""
    video_url: str = ""
    fail_reason: str = ""
    state: str = ""
    buttons: tuple[MidjourneyButton, ...] = field(default_factory=tuple)
    properties: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MidjourneyTask":
        status_raw = str(payload.get("status") or "NOT_START").upper()
        try:
            status = MidjourneyTaskStatus(status_raw)
        except ValueError:
            status = MidjourneyTaskStatus.NOT_START
        properties = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
        prompt = str(
            payload.get("prompt")
            or payload.get("promptEn")
            or properties.get("finalPrompt")
            or properties.get("finalZhPrompt")
            or ""
        )
        buttons = tuple(
            MidjourneyButton.from_payload(item)
            for item in (payload.get("buttons") or [])
            if isinstance(item, dict) and item.get("customId")
        )
        return cls(
            task_id=str(payload.get("id") or payload.get("taskId") or ""),
            action=str(payload.get("action") or ""),
            status=status,
            progress=str(payload.get("progress") or ""),
            prompt=prompt,
            image_url=str(payload.get("imageUrl") or ""),
            video_url=str(payload.get("videoUrl") or ""),
            fail_reason=str(payload.get("failReason") or payload.get("description") or ""),
            state=str(payload.get("state") or ""),
            buttons=buttons,
            properties=dict(properties),
        )


_VIDEO_TYPE_RE = re.compile(r"^vid_1\.1_i2v_(480|720)$")
_IMAGE_DATA_RE = re.compile(r"^data:image/(png|jpe?g|webp);base64,", re.IGNORECASE)


def _required(value: str, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _task_id_from_response(response: Any, operation: str) -> str:
    if not isinstance(response, dict):
        raise RuntimeError(f"Midjourney {operation}: invalid response {response!r}")
    code = response.get("code")
    if code not in (None, 1, 21, 22, "1", "21", "22"):
        raise RuntimeError(
            f"Midjourney {operation} failed: {code} "
            f"{response.get('description') or response.get('message')}"
        )
    task_id = str(response.get("result") or response.get("taskId") or "").strip()
    if not task_id:
        raise RuntimeError(f"Midjourney {operation}: response has no task id: {response!r}")
    return task_id


def _image_input(value: str, field_name: str) -> str:
    image = _required(value, field_name)
    if image.startswith(("http://", "https://")) or _IMAGE_DATA_RE.match(image):
        return image
    raise ValueError(f"{field_name} must be an HTTP(S) URL or image data URL")


async def imagine(
    prompt: str,
    *,
    bot: MidjourneyBot = MidjourneyBot.MIDJOURNEY,
    speed: MidjourneySpeed = MidjourneySpeed.FAST,
    base64_array: list[str] | None = None,
    state: str | None = None,
) -> str:
    prompt = _required(prompt, "prompt")
    images = [_image_input(item, "base64_array item") for item in (base64_array or [])]
    payload: dict[str, Any] = {
        "botType": bot.value,
        "prompt": prompt,
        "accountFilter": {"modes": [speed.value]},
    }
    if images:
        payload["base64Array"] = images
    if state:
        payload["state"] = str(state)
    response = await comet_client.post(f"{speed.route_prefix}/mj/submit/imagine", payload)
    return _task_id_from_response(response, "imagine")


async def action(
    task_id: str,
    custom_id: str,
    *,
    enable_remix: bool = False,
    state: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "taskId": _required(task_id, "task_id"),
        "customId": _required(custom_id, "custom_id"),
        "enableRemix": bool(enable_remix),
    }
    if state:
        payload["state"] = str(state)
    response = await comet_client.post("/mj/submit/action", payload)
    return _task_id_from_response(response, "action")


async def change(
    task_id: str,
    action_type: MidjourneyChangeAction | str,
    *,
    index: int | None = None,
    state: str | None = None,
) -> str:
    try:
        selected = (
            action_type
            if isinstance(action_type, MidjourneyChangeAction)
            else MidjourneyChangeAction(str(action_type).upper())
        )
    except ValueError as exc:
        raise ValueError("action_type must be UPSCALE, VARIATION or REROLL") from exc

    payload: dict[str, Any] = {
        "action": selected.value,
        "taskId": _required(task_id, "task_id"),
    }
    if selected in {MidjourneyChangeAction.UPSCALE, MidjourneyChangeAction.VARIATION}:
        if index is None or int(index) not in {1, 2, 3, 4}:
            raise ValueError("index must be 1-4 for UPSCALE and VARIATION")
        payload["index"] = int(index)
    elif index is not None:
        raise ValueError("REROLL does not accept index")
    if state:
        payload["state"] = str(state)

    response = await comet_client.post("/mj/submit/change", payload)
    return _task_id_from_response(response, "change")


async def modal(
    task_id: str,
    *,
    prompt: str = "",
    mask_base64: str = "",
) -> str:
    payload: dict[str, Any] = {"taskId": _required(task_id, "task_id")}
    if prompt:
        payload["prompt"] = str(prompt)
    if mask_base64:
        payload["maskBase64"] = _image_input(mask_base64, "mask_base64")
    if len(payload) == 1:
        raise ValueError("Midjourney modal requires prompt or mask_base64")
    response = await comet_client.post("/mj/submit/modal", payload)
    return _task_id_from_response(response, "modal")


async def blend(
    images: list[str],
    *,
    dimensions: BlendDimensions = BlendDimensions.SQUARE,
    bot: MidjourneyBot = MidjourneyBot.MIDJOURNEY,
    prompt: str | None = None,
) -> str:
    if not 2 <= len(images) <= 5:
        raise ValueError("Midjourney blend requires 2-5 images")
    payload: dict[str, Any] = {
        "botType": bot.value,
        "base64Array": [_image_input(item, "blend image") for item in images],
        "dimensions": dimensions.value,
    }
    if prompt:
        payload["prompt"] = str(prompt).strip()
    response = await comet_client.post("/mj/submit/blend", payload)
    return _task_id_from_response(response, "blend")


async def describe(
    *,
    base64_image: str | None = None,
    image_url: str | None = None,
    bot: MidjourneyBot = MidjourneyBot.MIDJOURNEY,
) -> str:
    if bool(base64_image) == bool(image_url):
        raise ValueError("Provide exactly one of base64_image or image_url")
    payload: dict[str, Any] = {"botType": bot.value}
    if base64_image:
        payload["base64"] = _image_input(base64_image, "base64_image")
    else:
        payload["link"] = _image_input(str(image_url), "image_url")
    response = await comet_client.post("/mj/submit/describe", payload)
    return _task_id_from_response(response, "describe")


async def submit_editor(provider_payload: dict[str, Any]) -> str:
    """Submit the current Comet-native Midjourney editor payload unchanged.

    Comet documents `/mj/submit/edits` and identifies `maskBase64`, prompts,
    optional originals and transparent-edit controls. Its public index does not
    currently expose a stable fully enumerated schema. To avoid inventing field
    names, APIX validates the known invariants and forwards the native object
    without translating or silently dropping provider fields.
    """
    if not isinstance(provider_payload, dict):
        raise TypeError("provider_payload must be an object")
    payload = dict(provider_payload)
    prompt = str(payload.get("prompt") or payload.get("prompts") or "").strip()
    mask = str(payload.get("maskBase64") or "").strip()
    if not prompt:
        raise ValueError("Midjourney editor requires prompt or prompts")
    if not mask:
        raise ValueError("Midjourney editor requires maskBase64")
    _image_input(mask, "maskBase64")
    response = await comet_client.post("/mj/submit/edits", payload)
    return _task_id_from_response(response, "editor")


async def submit_video(
    image_url: str,
    *,
    prompt: str = "",
    video_type: str = "vid_1.1_i2v_480",
    mode: MidjourneyVideoMode = MidjourneyVideoMode.FAST,
    animate_mode: MidjourneyAnimateMode = MidjourneyAnimateMode.MANUAL,
    motion: MidjourneyMotion = MidjourneyMotion.LOW,
) -> str:
    image = _image_input(image_url, "image_url")
    if not _VIDEO_TYPE_RE.fullmatch(str(video_type)):
        raise ValueError("video_type must be vid_1.1_i2v_480 or vid_1.1_i2v_720")
    combined_prompt = " ".join(part for part in (image, str(prompt or "").strip()) if part)
    payload = {
        "prompt": combined_prompt,
        "videoType": str(video_type),
        "mode": mode.value,
        "animateMode": animate_mode.value,
        "motion": motion.value,
    }
    response = await comet_client.post("/mj/submit/video", payload)
    return _task_id_from_response(response, "video")


async def fetch_task(task_id: str) -> MidjourneyTask:
    response = await comet_client.get(f"/mj/task/{_required(task_id, 'task_id')}/fetch")
    if not isinstance(response, dict):
        raise RuntimeError(f"Midjourney fetch returned invalid payload: {response!r}")
    return MidjourneyTask.from_payload(response)


async def list_by_condition(task_ids: list[str]) -> list[MidjourneyTask]:
    ids = [_required(item, "task_id") for item in task_ids]
    if not ids:
        return []
    response = await comet_client.post("/mj/task/list-by-condition", {"ids": ids})
    if isinstance(response, dict):
        candidates = response.get("data") or response.get("result") or []
    else:
        candidates = response
    if not isinstance(candidates, list):
        raise RuntimeError(f"Midjourney list-by-condition returned invalid payload: {response!r}")
    return [MidjourneyTask.from_payload(item) for item in candidates if isinstance(item, dict)]


async def poll_image(task_id: str) -> str | None:
    task = await fetch_task(task_id)
    if task.status == MidjourneyTaskStatus.SUCCESS:
        if task.image_url:
            return task.image_url
        raise RuntimeError("Midjourney image task succeeded without imageUrl")
    if task.status in {MidjourneyTaskStatus.FAILURE, MidjourneyTaskStatus.CANCEL}:
        raise RuntimeError(task.fail_reason or f"Midjourney task {task.status.value.lower()}")
    if task.status == MidjourneyTaskStatus.MODAL:
        raise RuntimeError("__MODAL__")
    return None


async def poll_video(task_id: str) -> str | None:
    task = await fetch_task(task_id)
    if task.status == MidjourneyTaskStatus.SUCCESS:
        if task.video_url:
            return task.video_url
        raise RuntimeError("Midjourney video task succeeded without videoUrl")
    if task.status in {MidjourneyTaskStatus.FAILURE, MidjourneyTaskStatus.CANCEL}:
        raise RuntimeError(task.fail_reason or f"Midjourney task {task.status.value.lower()}")
    return None
