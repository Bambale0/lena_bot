"""Wan 3.0 / Prime: provider-neutral validated video input contract.

Source-of-truth:
  https://docs.kie.ai/market/wan/3-0-video
  https://docs.kie.ai/market/wan/3-0-video-prime
  Neironych /guide?lang=ru (its /v1/models remains the authority for availability).

No network or payment calls in this module. Upstream media dimensions, bytes,
ownership and duration must be independently validated before construction.
"""
from __future__ import annotations

import ipaddress
import math
from dataclasses import dataclass
from urllib.parse import urlsplit

WAN30_MODELS = frozenset({"wan/3-0-video", "wan/3-0-video-prime"})
WAN30_RESOLUTIONS = frozenset({"480p", "720p", "1080p"})
WAN30_ASPECT_RATIOS = frozenset({"adaptive", "16:9", "9:16", "4:3", "3:4", "1:1"})
WAN30_MAX_DURATION = 30


@dataclass(frozen=True, slots=True)
class Wan30Request:
    model: str
    prompt: str
    first_frame_url: str | None = None
    last_frame_url: str | None = None
    reference_image_urls: tuple[str, ...] = ()
    reference_video_urls: tuple[str, ...] = ()
    reference_audio_urls: tuple[str, ...] = ()
    reference_file_urls: tuple[str, ...] = ()
    reference_link_urls: tuple[str, ...] = ()
    reference_video_durations: tuple[float, ...] = ()
    reference_audio_durations: tuple[float, ...] = ()
    resolution: str = "720p"
    aspect_ratio: str = "adaptive"
    duration: int = 5
    audio: bool = True
    seed: int | None = None
    nsfw_checker: bool = True
    mode: str | None = None


def _https_url(value: str) -> None:
    parsed = urlsplit(str(value))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("reference URL must be https and contain no credentials")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("reference URL must be a public https address")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if not ip.is_global:
        raise ValueError("reference URL cannot target private or special-purpose IPs")


def wan30_mode(request: Wan30Request) -> str:
    if request.mode:
        return request.mode
    if request.first_frame_url:
        return "first_last" if request.last_frame_url else "first"
    if request.reference_video_urls or request.reference_image_urls or request.reference_audio_urls:
        return "reference"
    if request.reference_file_urls:
        return "file"
    if request.reference_link_urls:
        return "link"
    return "text"


def _media_seconds(urls: tuple[str, ...], durations: tuple[float, ...], *, label: str) -> float:
    if not urls:
        if durations:
            raise ValueError(f"{label} durations without references")
        return 0.0
    if len(urls) != len(durations):
        raise ValueError(f"{label} must have independently measured durations for every reference")
    if any(
        isinstance(d, bool) or not isinstance(d, (float, int))
        or not math.isfinite(d) or d <= 0
        for d in durations
    ):
        raise ValueError(f"{label} durations must be measured positive finite seconds")
    total = sum(durations)
    if total > 15:
        raise ValueError(f"{label} total must not exceed 15 seconds")
    return total


def validate_wan30_request(request: Wan30Request) -> tuple[str, float]:
    if request.model not in WAN30_MODELS:
        raise ValueError("Unknown Wan 3.0 model")
    prompt = str(request.prompt or "")
    if not prompt.strip() or len(prompt) > 4500:
        raise ValueError("Wan prompt must have 1-4500 characters")
    if request.resolution.lower() not in WAN30_RESOLUTIONS:
        raise ValueError("resolution must be 480p, 720p or 1080p")
    if request.aspect_ratio not in WAN30_ASPECT_RATIOS:
        raise ValueError("Unsupported Wan aspect_ratio")
    if type(request.duration) is not int or (
        request.duration != -1 and not 2 <= request.duration <= WAN30_MAX_DURATION
    ):
        raise ValueError("duration must be -1 (auto) or 2-30 seconds")
    if type(request.audio) is not bool or type(request.nsfw_checker) is not bool:
        raise ValueError("audio and nsfw_checker must be boolean")
    if request.seed is not None and (
        type(request.seed) is not int or not 0 <= request.seed <= 2_147_483_647
    ):
        raise ValueError("seed must be an integer from 0 to 2147483647")
    for refs, max_count, label in (
        (request.reference_image_urls, 10, "images"),
        (request.reference_video_urls, 5, "videos"),
        (request.reference_audio_urls, 5, "audios"),
        (request.reference_file_urls, 1, "files"),
        (request.reference_link_urls, 1, "links"),
    ):
        if len(refs) > max_count:
            raise ValueError(f"Wan allows at most {max_count} {label}")
        for url in refs:
            _https_url(url)
    for frame in (request.first_frame_url, request.last_frame_url):
        if frame:
            _https_url(frame)
    if request.last_frame_url and not request.first_frame_url:
        raise ValueError("last_frame_url requires first_frame_url")
    if request.first_frame_url and any((
        request.reference_image_urls,
        request.reference_video_urls,
        request.reference_audio_urls,
        request.reference_file_urls,
        request.reference_link_urls,
    )):
        raise ValueError("frames cannot be combined with reference media")
    if request.reference_file_urls and request.reference_link_urls:
        raise ValueError("file and link cannot be combined")
    duration_of_videos = _media_seconds(
        request.reference_video_urls, request.reference_video_durations,
        label="reference video",
    )
    _media_seconds(request.reference_audio_urls, request.reference_audio_durations, label="reference audio")
    if request.duration != -1 and request.duration + duration_of_videos > 30:
        raise ValueError("sum of video references and output cannot exceed 30 seconds")
    mode = wan30_mode(request)
    if mode not in {"text", "first", "first_last", "reference", "edit", "file", "link"}:
        raise ValueError("Unsupported Wan mode")
    if mode == "edit" and not request.reference_video_urls:
        raise ValueError("Wan video editing requires source video as Video1")
    if mode == "text" and any((
        request.first_frame_url,
        request.last_frame_url,
        request.reference_image_urls, request.reference_video_urls,
        request.reference_audio_urls, request.reference_file_urls,
        request.reference_link_urls,
    )):
        raise ValueError("Text mode cannot be combined with media")
    if mode in {"first", "first_last"} and not request.first_frame_url:
        raise ValueError("Wan frame mode requires first_frame_url")
    if mode == "reference" and not (
        request.reference_image_urls or request.reference_video_urls or request.reference_audio_urls
    ):
        raise ValueError("Wan reference mode requires references")
    if mode == "file" and not request.reference_file_urls:
        raise ValueError("Wan file mode requires reference file")
    if mode == "link" and not request.reference_link_urls:
        raise ValueError("Wan link mode requires reference link")
    return mode, duration_of_videos


def wan30_max_billable_seconds(request: Wan30Request) -> float:
    _mode, video_seconds = validate_wan30_request(request)
    # Auto reserves the full 30 s combined provider limit, including video input.
    return float(WAN30_MAX_DURATION if request.duration == -1 else request.duration + video_seconds)


def build_kie_wan30_payload(request: Wan30Request) -> dict:
    validate_wan30_request(request)
    data = {
        "prompt": request.prompt,
        "resolution": request.resolution.upper(),
        "aspect_ratio": request.aspect_ratio,
        "duration": request.duration,
        "audio": request.audio,
        "nsfw_checker": request.nsfw_checker,
    }
    for attr in ("first_frame_url", "last_frame_url"):
        value = getattr(request, attr)
        if value:
            data[attr] = value
    for attr in (
        "reference_image_urls", "reference_video_urls", "reference_audio_urls",
        "reference_file_urls", "reference_link_urls",
    ):
        urls = getattr(request, attr)
        if urls:
            data[attr] = list(urls)
    if request.seed is not None:
        data["seed"] = request.seed
    return {"model": request.model, "input": data}


def wan30_supported_by_neironych(request: Wan30Request) -> bool:
    mode, _ = validate_wan30_request(request)
    # Current native edit derives output length from the input clip and forbids
    # duration. Keep fixed-duration quoted edits on KIE to preserve the order.
    if mode == "edit":
        return False
    if request.model == "wan/3-0-video-prime" and (
        request.duration < 4
        or request.aspect_ratio not in {"16:9", "1:1", "9:16"}
        or not request.audio
        or request.seed is not None
        or request.first_frame_url is not None
        or request.last_frame_url is not None
        or (request.reference_audio_urls and not (
            request.reference_image_urls or request.reference_video_urls
        ))
    ):
        return False
    # Neironych public guide has no verified file/link input fields.
    return (
        mode not in {"file", "link"}
        and not (request.reference_file_urls or request.reference_link_urls)
        # The public Neironych Wan contract does not advertise custom safety
        # toggle support. Never silently discard an explicit opt-out.
        and request.nsfw_checker is True
        # Neironych disallows ratio with input frames. Respect an explicit
        # ratio request by using the KIE contract instead of dropping it.
        and not (
            request.first_frame_url and request.aspect_ratio != "adaptive"
        )
    )


def build_neironych_wan30_payload(request: Wan30Request, *, provider_model: str) -> dict:
    if not wan30_supported_by_neironych(request):
        raise ValueError("Wan input options are not supported by the Neironych contract")
    if not provider_model or not provider_model.strip():
        raise ValueError("Neironych Wan model ID must be verified from /v1/models")
    validate_wan30_request(request)
    result = {
        "model": provider_model,
        "prompt": request.prompt,
        "duration": request.duration,
        "resolution": request.resolution.lower(),
    }
    if request.model != "wan/3-0-video-prime":
        result["generate_audio"] = request.audio
    if not request.first_frame_url:
        result["aspect_ratio"] = request.aspect_ratio
    if request.first_frame_url:
        result["start_image"] = {"url": request.first_frame_url}
    if request.last_frame_url:
        result["end_image"] = {"url": request.last_frame_url}
    for name, dest in (
        ("reference_image_urls", "reference_images"),
        ("reference_video_urls", "reference_videos"),
        ("reference_audio_urls", "reference_audios"),
    ):
        urls = getattr(request, name)
        if urls:
            result[dest] = [{"url": url} for url in urls]
    if request.seed is not None:
        result["seed"] = request.seed
    return result
