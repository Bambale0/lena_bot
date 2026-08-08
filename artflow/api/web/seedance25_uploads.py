from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile

from api.public_files import save_public_file
from api.web.deps import error_response, get_web_user_or_none, ok

router = APIRouter(tags=["web"])

MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_AUDIO_BYTES = 15 * 1024 * 1024

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".m4a", ".ogg"}


def _kind_and_limit(file: UploadFile) -> tuple[str | None, int, str | None]:
    suffix = Path(str(file.filename or "")).suffix.lower()
    content_type = str(file.content_type or "").lower()

    if suffix in _IMAGE_EXTENSIONS or content_type.startswith("image/"):
        if suffix and suffix not in _IMAGE_EXTENSIONS:
            return None, 0, "Seedance 2.5: unsupported image format"
        return "image", MAX_IMAGE_BYTES, None
    if suffix in _VIDEO_EXTENSIONS or content_type.startswith("video/"):
        if suffix and suffix not in _VIDEO_EXTENSIONS:
            return None, 0, "Seedance 2.5: video must be MP4, MOV or MKV"
        return "video", MAX_VIDEO_BYTES, None
    if suffix in _AUDIO_EXTENSIONS or content_type.startswith("audio/"):
        if suffix and suffix not in _AUDIO_EXTENSIONS:
            return None, 0, "Seedance 2.5: unsupported audio format"
        return "audio", MAX_AUDIO_BYTES, None
    return None, 0, "Seedance 2.5: unsupported reference format"


@router.post("/seedance25/upload-reference")
async def upload_seedance25_reference(
    file: UploadFile = File(...),
    user=Depends(get_web_user_or_none),
):
    if user is None:
        return error_response(401, "Authentication required")

    kind, limit, error = _kind_and_limit(file)
    if error:
        return error_response(422, error)

    data = await file.read()
    if not data:
        return error_response(422, "Empty file")
    if len(data) > limit:
        return error_response(413, f"Seedance 2.5 {kind} reference is too large")

    content_type = str(file.content_type or "application/octet-stream")
    url = save_public_file(data, content_type, subdir=f"seedance25/{kind}")
    return ok({"url": url, "kind": kind, "content_type": content_type, "size": len(data)})
