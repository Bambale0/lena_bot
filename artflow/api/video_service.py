# api/video_service.py
"""
Генерация видео: Kling 3.0, Kling 2.6 Motion Control, Grok Video.
Все модели — асинхронные, возвращают task_id + polling.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from api import comet_client

logger = logging.getLogger(__name__)


class VideoModel(StrEnum):
    KLING_30 = "kling-3.0"
    KLING_26_MOTION = "kling-2.6-motion"
    GROK_VIDEO = "grok-video"


class MotionDirection(StrEnum):
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP = "tilt_up"
    TILT_DOWN = "tilt_down"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    ORBIT_LEFT = "orbit_left"
    ROLL_CW = "roll_clockwise"

    def label(self) -> str:
        _labels = {
            "pan_left": "◀ Pan Left",
            "pan_right": "▶ Pan Right",
            "tilt_up": "▲ Tilt Up",
            "tilt_down": "▼ Tilt Down",
            "zoom_in": "🔍 Zoom In",
            "zoom_out": "🔎 Zoom Out",
            "orbit_left": "↺ Orbit",
            "roll_clockwise": "↻ Roll",
        }
        return _labels.get(self.value, self.value)


@dataclass
class VideoResult:
    task_id: str
    provider: str  # "kling" | "grok"


async def generate_video(
    model: VideoModel,
    prompt: str,
    image_url: str | None = None,
    motion: MotionDirection | None = None,
    duration: int = 5,
) -> VideoResult:
    if model == VideoModel.GROK_VIDEO:
        return await _grok_generate(prompt)
    elif model == VideoModel.KLING_26_MOTION:
        return await _kling_motion_generate(prompt, image_url, motion)
    else:
        return await _kling_generate(model, prompt, image_url, duration)


async def _kling_generate(
    model: VideoModel,
    prompt: str,
    image_url: str | None,
    duration: int,
) -> VideoResult:
    version_map = {VideoModel.KLING_30: "2.0"}  # kling 3.0 maps to api v2.0
    version = version_map.get(model, "1.6")

    if image_url:
        path = "/kling/v1/videos/image2video"
        payload = {
            "model_name": f"kling-v{version}",
            "image_url": image_url,
            "prompt": prompt,
            "duration": str(duration),
            "mode": "pro",
        }
    else:
        path = "/kling/v1/videos/text2video"
        payload = {
            "model_name": f"kling-v{version}",
            "prompt": prompt,
            "duration": str(duration),
            "mode": "pro",
        }

    resp = await comet_client.post(path, payload)
    task_id = resp["data"]["task_id"]
    logger.info("Kling task created: %s", task_id)
    return VideoResult(task_id=task_id, provider="kling")


async def _kling_motion_generate(
    prompt: str,
    image_url: str | None,
    motion: MotionDirection | None,
) -> VideoResult:
    """Kling 2.6 with camera control / motion."""
    payload: dict = {
        "model_name": "kling-v1.6",
        "prompt": prompt,
        "duration": "5",
        "mode": "pro",
    }
    if image_url:
        payload["image_url"] = image_url

    if motion:
        payload["camera_control"] = {
            "type": "preset_motion",
            "config": {"horizontal": 0, "vertical": 0, "zoom": 0, "tilt": 0, "pan": 0, "roll": 0},
        }
        # Map our enum to Kling camera params
        motion_config = payload["camera_control"]["config"]
        if motion == MotionDirection.PAN_LEFT:
            motion_config["pan"] = -10
        elif motion == MotionDirection.PAN_RIGHT:
            motion_config["pan"] = 10
        elif motion == MotionDirection.TILT_UP:
            motion_config["tilt"] = 10
        elif motion == MotionDirection.TILT_DOWN:
            motion_config["tilt"] = -10
        elif motion == MotionDirection.ZOOM_IN:
            motion_config["zoom"] = 10
        elif motion == MotionDirection.ZOOM_OUT:
            motion_config["zoom"] = -10
        elif motion == MotionDirection.ORBIT_LEFT:
            motion_config["horizontal"] = -10
        elif motion == MotionDirection.ROLL_CW:
            motion_config["roll"] = 10

    path = "/kling/v1/videos/image2video" if image_url else "/kling/v1/videos/text2video"
    resp = await comet_client.post(path, payload)
    task_id = resp["data"]["task_id"]
    logger.info("Kling motion task: %s", task_id)
    return VideoResult(task_id=task_id, provider="kling")


async def _grok_generate(prompt: str) -> VideoResult:
    resp = await comet_client.post(
        "/v1/video/generate",
        {"model": "grok-2-vision", "prompt": prompt},
    )
    task_id = resp.get("task_id") or resp.get("id")
    logger.info("Grok video task: %s", task_id)
    return VideoResult(task_id=str(task_id), provider="grok")


async def poll_kling_status(task_id: str) -> str | None:
    """Returns video URL when done, None if still processing."""
    resp = await comet_client.get(f"/kling/v1/videos/text2video/{task_id}")
    task_status = resp.get("data", {}).get("task_status")
    if task_status == "succeed":
        works = resp["data"].get("task_result", {}).get("videos", [])
        if works:
            return works[0].get("url")
    if task_status == "failed":
        raise RuntimeError(f"Kling failed: {resp.get('data', {}).get('task_status_msg', 'error')}")
    return None


async def poll_grok_status(task_id: str) -> str | None:
    resp = await comet_client.get(f"/v1/video/generate/{task_id}")
    status = resp.get("status")
    if status == "succeeded":
        return resp.get("video_url") or resp.get("url")
    if status in ("failed", "error"):
        raise RuntimeError(f"Grok video failed: {resp.get('message', 'error')}")
    return None
