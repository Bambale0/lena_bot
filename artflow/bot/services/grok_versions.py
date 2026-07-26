"""Runtime separation for Grok Imagine Video and Grok Imagine Video 1.5."""
from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from typing import Any

from api import kieai_client, video_service
from bot.keyboards import models as model_keyboards
from bot.keyboards.models import VIDEO_CAPS, VIDEO_MODEL_DESC
from bot.ui.model_labels import model_display_name
from db import repository as repo

GROK_LEGACY_T2V = "grok-imagine/text-to-video"
GROK_LEGACY_I2V = "grok-imagine/image-to-video"
GROK_15 = "grok-imagine-video-1-5-preview"


@dataclass(frozen=True)
class _ExternalVideoModel:
    value: str


class _VideoModelProxy:
    def __init__(self, enum_cls: Any) -> None:
        self._enum_cls = enum_cls

    def __call__(self, value: Any):
        raw = getattr(value, "value", value)
        if str(raw) == GROK_15:
            return _ExternalVideoModel(GROK_15)
        return self._enum_cls(raw)

    def __getattr__(self, name: str):
        return getattr(self._enum_cls, name)

    def __iter__(self):
        return iter(self._enum_cls)


def _clone_cost(row: Any, model_key: str):
    cloned = copy(row)
    try:
        cloned.model_key = model_key
        cloned.display_name = model_display_name(GROK_15)
    except Exception:
        return row
    return cloned


def _grok15_key_from_legacy(key: str) -> str:
    if key == GROK_LEGACY_T2V:
        return GROK_15
    prefix = f"{GROK_LEGACY_T2V}::"
    if key.startswith(prefix):
        return f"{GROK_15}::{key[len(prefix):]}"
    return key


def _install_repository_aliases() -> None:
    original_all = repo.get_all_model_costs
    if not getattr(original_all, "__grok_versions__", False):
        async def get_all_model_costs(*args: Any, **kwargs: Any):
            rows = list(await original_all(*args, **kwargs))
            if any(str(getattr(row, "model_key", "")) == GROK_15 for row in rows):
                return rows
            additions = []
            for row in rows:
                key = str(getattr(row, "model_key", ""))
                mapped = _grok15_key_from_legacy(key)
                if mapped != key:
                    additions.append(_clone_cost(row, mapped))
            return rows + additions

        get_all_model_costs.__grok_versions__ = True  # type: ignore[attr-defined]
        repo.get_all_model_costs = get_all_model_costs

    original_get = repo.get_model_cost
    if not getattr(original_get, "__grok_versions__", False):
        async def get_model_cost(session: Any, model_key: str, *args: Any, **kwargs: Any):
            row = await original_get(session, model_key, *args, **kwargs)
            if row is not None or model_key != GROK_15:
                return row
            legacy = await original_get(session, GROK_LEGACY_T2V, *args, **kwargs)
            return _clone_cost(legacy, GROK_15) if legacy is not None else None

        get_model_cost.__grok_versions__ = True  # type: ignore[attr-defined]
        repo.get_model_cost = get_model_cost

    original_resolve = repo.resolve_video_model_cost
    if not getattr(original_resolve, "__grok_versions__", False):
        async def resolve_video_model_cost(session: Any, model_key: str, *args: Any, **kwargs: Any):
            row = await original_resolve(session, model_key, *args, **kwargs)
            if row is not None or model_key != GROK_15:
                return row
            legacy = await original_resolve(session, GROK_LEGACY_T2V, *args, **kwargs)
            return _clone_cost(legacy, GROK_15) if legacy is not None else None

        resolve_video_model_cost.__grok_versions__ = True  # type: ignore[attr-defined]
        repo.resolve_video_model_cost = resolve_video_model_cost


def _install_generation_route() -> None:
    real_enum = video_service.VideoModel
    if isinstance(real_enum, _VideoModelProxy):
        return

    proxy = _VideoModelProxy(real_enum)
    video_service.VideoModel = proxy  # type: ignore[assignment]
    original_generate = video_service.generate_video

    async def generate_video(model: Any, prompt: str, **kwargs: Any):
        model_key = str(getattr(model, "value", model))
        if model_key != GROK_15:
            return await original_generate(model, prompt, **kwargs)

        image_url = kwargs.get("image_url")
        if isinstance(image_url, str):
            image_urls = [image_url] if image_url else []
        else:
            image_urls = [str(item) for item in (image_url or []) if item]

        payload_input: dict[str, Any] = {
            "prompt": str(prompt or "").strip(),
            "duration": max(1, min(15, int(kwargs.get("duration") or 8))),
            "aspect_ratio": kwargs.get("aspect_ratio") or ("auto" if image_urls else "16:9"),
            "resolution": kwargs.get("resolution") or "480p",
            "nsfw_checker": False,
        }
        if image_urls:
            payload_input["image_urls"] = image_urls[:7]

        response = await kieai_client.create_task(
            {"model": GROK_15, "input": payload_input},
            callback_url=kwargs.get("callback_url"),
        )
        data = response.get("data") if isinstance(response, dict) else None
        data = data if isinstance(data, dict) else {}
        task_id = str(data.get("taskId") or (response.get("taskId") if isinstance(response, dict) else "") or "")
        if not task_id:
            raise RuntimeError(f"Grok 1.5 returned no taskId: {response!r}")
        return video_service.VideoResult(
            task_id=task_id,
            provider="kieai",
            uses_webhook=bool(kwargs.get("callback_url")),
        )

    generate_video.__grok_versions__ = True  # type: ignore[attr-defined]
    video_service.generate_video = generate_video


def _install_picker_groups() -> None:
    """Add Grok 1.5 to both relevant legacy picker categories."""
    for group_key, model_keys in model_keyboards._VIDEO_GROUPS:
        if group_key in {"fast", "i2v"} and GROK_15 not in model_keys:
            legacy_anchor = GROK_LEGACY_T2V if group_key == "fast" else GROK_LEGACY_I2V
            try:
                index = [str(getattr(item, "value", item)) for item in model_keys].index(legacy_anchor) + 1
            except ValueError:
                index = len(model_keys)
            model_keys.insert(index, GROK_15)


def install_grok_versions() -> None:
    """Restore Grok 1 and register Grok 1.5 as a separate public model."""
    VIDEO_CAPS[GROK_LEGACY_T2V] = {
        "modes": ["text"],
        "duration_options": [6, 10, 15, 20, 30],
        "aspect_ratios": ["2:3", "3:2", "1:1", "16:9", "9:16"],
        "has_resolution": True,
        "resolutions": ["480p", "720p"],
        "mode_options": ["fun", "normal", "spicy"],
        "billing_mode": "per_second",
    }
    VIDEO_CAPS[GROK_LEGACY_I2V] = {
        "modes": ["image"],
        "duration_options": [6, 10, 15, 20, 30],
        "aspect_ratios": ["2:3", "3:2", "1:1", "16:9", "9:16"],
        "aspect_ratio_min_refs": 2,
        "has_resolution": True,
        "resolutions": ["480p", "720p"],
        "mode_options": ["fun", "normal"],
        "max_refs": 7,
        "billing_mode": "per_second",
    }
    VIDEO_CAPS[GROK_15] = {
        "modes": ["text", "image"],
        "duration_options": list(range(1, 16)),
        "aspect_ratios": ["auto", "1:1", "16:9", "9:16", "3:2", "2:3"],
        "has_resolution": True,
        "resolutions": ["480p", "720p"],
        "max_refs": 7,
        "native_audio": True,
        "billing_mode": "per_second",
    }
    VIDEO_MODEL_DESC[GROK_LEGACY_T2V] = "⚡ Grok Imagine Video · генерация по тексту"
    VIDEO_MODEL_DESC[GROK_LEGACY_I2V] = "⚡ Grok Imagine Video · оживление изображений"
    VIDEO_MODEL_DESC[GROK_15] = "🆕 NEW · Grok Imagine Video 1.5 · текст или до 7 фото · нативный звук"

    _install_picker_groups()
    _install_repository_aliases()
    _install_generation_route()
