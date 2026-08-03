from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import HTTPException

from core.config import settings

ASSET_TOKEN_TTL_SECONDS = 24 * 60 * 60


def _asset_secret() -> bytes:
    secret = (
        getattr(settings, "WEBHOOK_SECRET", "")
        or getattr(settings, "KIE_WEBHOOK_SECRET", "")
        or getattr(settings, "BOT_TOKEN", "")
    )
    if not secret:
        raise HTTPException(status_code=503, detail="Asset signing secret is not configured")
    return str(secret).encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _sign(payload: str) -> str:
    digest = hmac.new(_asset_secret(), payload.encode("utf-8"), hashlib.sha256).digest()
    return _b64url(digest)


def sign_uploaded_asset(
    *,
    user_id: int,
    url: str,
    kind: str,
    filename: str | None = None,
    content_type: str | None = None,
    size: int | None = None,
) -> str:
    payload = {
        "v": 1,
        "uid": int(user_id),
        "url": str(url),
        "kind": str(kind),
        "filename": filename or "",
        "content_type": content_type or "",
        "size": int(size or 0),
        "iat": int(time.time()),
    }
    encoded = _b64url(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return f"apixasset.{encoded}.{_sign(encoded)}"


def verify_uploaded_asset(
    asset_id: str,
    *,
    user_id: int,
    expected_kind: str | None = None,
) -> dict[str, Any]:
    raw = str(asset_id or "").strip()
    parts = raw.split(".")
    if len(parts) != 3 or parts[0] != "apixasset":
        raise HTTPException(status_code=422, detail="Invalid uploaded asset")
    encoded, signature = parts[1], parts[2]
    expected_signature = _sign(encoded)
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=422, detail="Invalid uploaded asset signature")
    try:
        payload = json.loads(_unb64url(encoded).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid uploaded asset payload") from exc
    if int(payload.get("uid") or 0) != int(user_id):
        raise HTTPException(status_code=403, detail="Uploaded asset belongs to another user")
    if expected_kind and str(payload.get("kind") or "") != expected_kind:
        raise HTTPException(status_code=422, detail=f"Uploaded asset must be {expected_kind}")
    issued_at = int(payload.get("iat") or 0)
    if issued_at <= 0 or time.time() - issued_at > ASSET_TOKEN_TTL_SECONDS:
        raise HTTPException(status_code=422, detail="Uploaded asset expired. Please upload the photo again")
    url = str(payload.get("url") or "")
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("/")):
        raise HTTPException(status_code=422, detail="Uploaded asset URL is invalid")
    return payload


def image_kind_from_upload(data: bytes, content_type: str | None, filename: str | None = None) -> bool:
    content = (content_type or "").split(";", 1)[0].lower().strip()
    name = (filename or "").lower().strip()
    ext_ok = name.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".avif"))
    mime_ok = content in {
        "",
        "application/octet-stream",
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "image/heif",
        "image/avif",
    }
    magic_ok = (
        data.startswith(b"\xff\xd8\xff")
        or data.startswith(b"\x89PNG\r\n\x1a\n")
        or (data.startswith(b"RIFF") and b"WEBP" in data[:16])
        or (len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"avif"})
    )
    return bool(mime_ok and (magic_ok or ext_ok))
