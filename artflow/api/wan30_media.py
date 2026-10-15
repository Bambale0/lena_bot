"""Durable Wan3 provider MP4 results. Never mark done with expiring provider URLs."""
from __future__ import annotations

from api.public_files import local_upload_path_from_url, mirror_url


async def mirror_wan30_result(url: str) -> str:
    if not str(url or "").startswith("https://"):
        raise ValueError("Wan3 result must be a public HTTPS video URL")
    mirrored = await mirror_url(url, subdir="provider-results")
    file = local_upload_path_from_url(mirrored)
    if not file or not file.exists() or not file.is_file():
        raise RuntimeError("Wan3 result could not be stored in APIX")
    if file.suffix.lower() not in {".mp4", ".mov", ".webm"}:
        raise RuntimeError("Wan3 result did not resolve to a supported video file")
    return mirrored
