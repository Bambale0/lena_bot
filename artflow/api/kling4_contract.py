"""Exact KIE Kling 4 contracts. No transport, wallet or runtime configuration.

Sources: docs.kie.ai/market/kling/v4-{reference,keyframe}-to-video.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from api.wan30_contract import _https_url

REFERENCE_MODEL = "kling-4.0/reference-to-video"
KEYFRAME_MODEL = "kling-4.0/keyframe-to-video"
KLING4_MODELS = frozenset({REFERENCE_MODEL, KEYFRAME_MODEL})
NAME = re.compile(r"^[\u4E00-\u9FA5A-Za-z0-9_]{1,20}$")
RESERVED = re.compile(
    r"^(?:(?:image|video|keyframe|object|audio)_\d+|first_frame|last_frame)$", re.I
)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Kling4Element(StrictInput):
    name: str
    image_urls: list[str] = Field(default_factory=list, max_length=4)
    video_url: str | None = None
    tag: Literal["character", "animal", "prop", "costume", "scene", "effect", "others"] | None = (
        None
    )
    description: str | None = Field(default=None, max_length=100)
    voice_url: str | None = None

    @model_validator(mode="after")
    def source(self):
        if bool(self.image_urls) == bool(self.video_url):
            raise ValueError("Element requires image_urls or video_url, exclusively")
        if self.image_urls and not 2 <= len(self.image_urls) <= 4:
            raise ValueError("Image element requires 2–4 images")
        if self.video_url and self.tag not in (None, "character"):
            raise ValueError("Video element must be a character")
        if self.voice_url and self.tag not in (None, "character"):
            raise ValueError("A bound voice requires a character")
        return self


class Kling4Voice(StrictInput):
    name: str
    audio_url: str


class Kling4Input(StrictInput):
    duration: StrictInt = Field(default=5, ge=3, le=30)
    resolution: Literal["720p", "1080p"] = "720p"
    aspect_ratio: Literal["auto", "16:9", "9:16", "1:1", "21:9"] | None = None
    image_urls: list[str] = Field(default_factory=list, max_length=10)
    video_urls: list[str] = Field(default_factory=list, max_length=5)
    keep_original_sound: StrictBool = False
    elements: list[Kling4Element] = Field(default_factory=list, max_length=7)
    voices: list[Kling4Voice] = Field(default_factory=list, max_length=3)
    first_frame_url: str | None = None
    keyframe_urls: list[str] = Field(default_factory=list, max_length=8)
    last_frame_url: str | None = None


def media_roles(data: Kling4Input) -> list[tuple[str, str, bool]]:
    """URL, media kind, whether it is an appearance video element."""
    roles = [(url, "image", False) for url in data.image_urls + data.keyframe_urls]
    roles += [(url, "image", False) for url in (data.first_frame_url, data.last_frame_url) if url]
    roles += [(url, "video", False) for url in data.video_urls]
    for element in data.elements:
        roles += [(url, "image", False) for url in element.image_urls]
        if element.video_url:
            roles.append((element.video_url, "video", True))
        if element.voice_url:
            roles.append((element.voice_url, "audio", False))
    roles += [(voice.audio_url, "audio", False) for voice in data.voices]
    return roles


def _validate_mentions(prompt: str, names: set[str]) -> None:
    ordered = sorted(names, key=len, reverse=True)
    for match in re.finditer("@", prompt):
        tail = prompt[match.end() :]
        for name in ordered:
            if tail.startswith(name) and (
                len(tail) == len(name) or not (tail[len(name)].isalnum() or tail[len(name)] == "_")
            ):
                break
        else:
            raise ValueError(
                "Промпт содержит @ссылку на отсутствующий материал; проверь имя и регистр"
            )


def build_kling4_payload(model: str, prompt: str, data: Kling4Input) -> dict:
    if model not in KLING4_MODELS:
        raise ValueError("Unknown Kling 4 model")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8000:
        raise ValueError("Kling 4 prompt must have 1–8000 characters")
    names: set[str] = set()
    out = {"prompt": prompt, "duration": data.duration, "resolution": data.resolution}
    if model == REFERENCE_MODEL:
        if data.first_frame_url or data.keyframe_urls or data.last_frame_url:
            raise ValueError("Reference mode does not accept keyframes")
        if sum(map(len, (data.image_urls, data.video_urls, data.elements, data.voices))) > 15:
            raise ValueError("Kling 4 supports at most 15 materials")
        video_elements = sum(bool(element.video_url) for element in data.elements)
        if video_elements > 3 or len(data.video_urls) + video_elements > 5:
            raise ValueError("At most 3 video elements and 5 videos combined")
        seen = set()
        for item in [*data.elements, *data.voices]:
            if (
                not NAME.fullmatch(item.name)
                or RESERVED.fullmatch(item.name)
                or item.name.lower() in seen
            ):
                raise ValueError(
                    "Material names must be unique and non-reserved: Latin/Chinese letters, digits, underscore; 1–20 characters"
                )
            names.add(item.name)
            seen.add(item.name.lower())
        names.update(f"image_{i+1}" for i in range(len(data.image_urls)))
        names.update(f"video_{i+1}" for i in range(len(data.video_urls)))
        for key in ("image_urls", "video_urls", "elements", "voices"):
            values = getattr(data, key)
            if values:
                out[key] = [
                    v.model_dump(exclude_none=True, exclude_defaults=True)
                    if isinstance(v, BaseModel)
                    else v
                    for v in values
                ]
        if data.video_urls:
            out["keep_original_sound"] = data.keep_original_sound
        out["aspect_ratio"] = data.aspect_ratio or ("auto" if names else "16:9")
    else:
        if (
            data.image_urls
            or data.video_urls
            or data.elements
            or data.voices
            or data.keep_original_sound
        ):
            raise ValueError("Keyframe mode does not accept reference materials")
        if (data.keyframe_urls or data.last_frame_url) and not data.first_frame_url:
            raise ValueError("First frame is required before middle or last frames")
        frames = len(data.keyframe_urls) + bool(data.first_frame_url) + bool(data.last_frame_url)
        if frames > min(10, data.duration + 1):
            raise ValueError("Too many keyframes for output duration")
        for key, name in (("first_frame_url", "first_frame"), ("last_frame_url", "last_frame")):
            if getattr(data, key):
                out[key] = getattr(data, key)
                names.add(name)
        if data.keyframe_urls:
            out["keyframe_urls"] = list(data.keyframe_urls)
            names.update(f"keyframe_{i+1}" for i in range(len(data.keyframe_urls)))
        if not frames:
            out["aspect_ratio"] = data.aspect_ratio or "16:9"
    for url, _kind, _element in media_roles(data):
        _https_url(url)
    _validate_mentions(prompt, names)
    return {"model": model, "input": out}
