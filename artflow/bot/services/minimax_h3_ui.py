"""Presentation helpers for the unified MiniMax H3 Telegram flow."""
from __future__ import annotations

from typing import Any

from api.minimax_h3_adapter import PUBLIC_MODEL


def _list_count(value: Any) -> int:
    if not value:
        return 0
    if isinstance(value, (list, tuple, set)):
        return len([item for item in value if item])
    return 1


def _image_count(data: dict[str, Any]) -> int:
    refs = data.get("ref_file_ids")
    if isinstance(refs, list) and refs:
        return len([item for item in refs if item])
    return _list_count(data.get("image_url") or data.get("image_file_id"))


def install_minimax_h3_handler_presentation(video_gen: Any) -> None:
    """Prevent H3 reference URLs from being labelled as Gemini Omni IDs."""
    if getattr(video_gen, "_minimax_h3_presentation_installed", False):
        return

    original_summary = video_gen._params_summary
    original_hint = video_gen._video_params_hint

    def params_summary(data: dict[str, Any]) -> str:
        if str(data.get("model_key") or "") != PUBLIC_MODEL:
            return original_summary(data)

        images = _image_count(data)
        videos = _list_count(data.get("reference_video_url")) + _list_count(data.get("character_ids"))
        audios = _list_count(data.get("audio_ids"))
        parts = [
            f"{data['duration']} сек" if data.get("duration") else None,
            f"качество {data['resolution']}" if data.get("resolution") else None,
            data.get("aspect_ratio") if data.get("aspect_ratio") else None,
            f"фото: {images}" if images else None,
            f"видео: {videos}" if videos else None,
            f"аудио: {audios}" if audios else None,
        ]
        return " · ".join(str(part) for part in parts if part) or "по умолчанию"

    def params_hint(model_key: str, data: dict[str, Any]) -> str:
        if str(model_key) != PUBLIC_MODEL:
            return original_hint(model_key, data)
        return (
            "MiniMax H3 сам выбирает Text-to-Video, первый/последний кадр или Reference-to-Video "
            "по добавленным материалам. Здесь меняются только длительность, качество и формат. "
            "Когда всё готово, нажми <b>Далее</b>."
        )

    video_gen._params_summary = params_summary
    video_gen._video_params_hint = params_hint
    video_gen._minimax_h3_presentation_installed = True
