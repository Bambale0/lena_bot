"""Authenticated, per-generation Kie Seedance webhook correlation."""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core.config import settings


def _mac(gen_id: int) -> str:
    key = str(settings.KIE_WEBHOOK_HMAC_KEY or "").strip()
    if not key:
        raise ValueError("Dedicated Kie webhook HMAC key is not configured")
    key = key.encode("utf-8")
    return hmac.new(key, f"seedance-kie-v1:{gen_id}".encode("ascii"), hashlib.sha256).hexdigest()


def callback_url_for_generation(url: str, gen_id: int | None) -> str:
    if gen_id is None:
        return url
    if gen_id <= 0:
        raise ValueError("Invalid generation ID")
    source = urlsplit(url)
    params = [(k,v) for k,v in parse_qsl(source.query, keep_blank_values=True)
              if k not in ("apix_generation_id", "apix_generation_sig")]
    params.extend((
        ("apix_generation_id", str(gen_id)),
        ("apix_generation_sig", _mac(gen_id)),
    ))
    return urlunsplit((
        source.scheme, source.netloc, source.path, urlencode(params), source.fragment,
    ))


def verify_generation_signature(gen_id: int | None, signature: str | None) -> bool:
    if not isinstance(gen_id, int) or gen_id <= 0:
        return False
    if not isinstance(signature, str) or len(signature) != 64:
        return False
    if not str(settings.KIE_WEBHOOK_HMAC_KEY or "").strip():
        return False
    return hmac.compare_digest(signature, _mac(gen_id))
