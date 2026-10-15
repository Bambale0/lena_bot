"""Durable Wan3 provider MP4 results. Never mark done with expiring provider URLs."""
from __future__ import annotations

import math

from api.media_gateway import MediaKind, probe_local_media
from api.public_files import local_upload_path_from_url, mirror_url


async def mirror_wan30_result(url: str) -> str:
    if not str(url or "").startswith("https://"):
        raise ValueError("Wan3 result must be a public HTTPS video URL")
    mirrored = await mirror_url(url, subdir="provider-results")
    file = local_upload_path_from_url(mirrored)
    if not file or not file.exists() or not file.is_file():
        raise RuntimeError("Wan3 result could not be stored in APIX")
    if file.suffix.lower() != ".mp4":
        raise RuntimeError("Wan3 result did not resolve to a playable MP4 video file")
    try:
        # Reject HTML error pages with an .mp4 filename and QuickTime MOV
        # masquerading as MP4 before publishing a final result to users.
        with file.open("rb") as stream:
            header = stream.read(16)
        if len(header) < 12 or header[4:8] != b"ftyp" or header[8:12] == b"qt  ":
            raise RuntimeError("Wan3 result is not an MP4 container")
        metadata = await probe_local_media(file, MediaKind.VIDEO)
        duration = metadata.duration_seconds
        if (not metadata.width or not metadata.height or duration is None
                or not math.isfinite(duration) or duration <= 0):
            raise RuntimeError("Wan3 MP4 media probe did not find a playable video")
    except (OSError, ValueError, RuntimeError) as exc:
        raise RuntimeError("Wan3 result is not a verified playable MP4 video") from exc
    return mirrored
