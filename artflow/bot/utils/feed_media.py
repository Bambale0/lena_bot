from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from api.public_files import public_url_is_available
from core.config import settings


def _json_url_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item or "").strip()]
    return []


def canonical_generation_result_url(generation: Any) -> str | None:
    """Return the same primary media URL the public Mini App feed renders.

    Multi-result generations keep their ordered canonical media in ``result_urls``.
    ``result_url`` is a legacy convenience field and can become stale when a task
    is mirrored/recovered. Prefer the first available item from ``result_urls`` so
    Telegram deep links cannot open a different work than the feed card the user
    shared.
    """

    result_urls = _json_url_list(getattr(generation, "result_urls", None))
    for url in result_urls:
        if public_url_is_available(url):
            return url

    primary = str(getattr(generation, "result_url", "") or "").strip()
    if primary and public_url_is_available(primary):
        return primary

    # Preserve deterministic identity even when availability cannot currently be
    # proven. Delivery code will handle the unavailable URL with its normal
    # fallback, but it must still point at this generation rather than another one.
    if result_urls:
        return result_urls[0]
    return primary or None


async def repair_generation_primary_result_url(session: Any, generation: Any) -> str | None:
    """Align legacy ``result_url`` with the canonical feed media for old posts."""

    canonical = canonical_generation_result_url(generation)
    current = str(getattr(generation, "result_url", "") or "").strip() or None
    if canonical and canonical != current:
        generation.result_url = canonical
        await session.commit()
    return canonical


def generation_result_reference_urls(generation: Any) -> list[str]:
    """Every known output is scene-only, including a stale/unavailable primary."""
    urls = _json_url_list(getattr(generation, "result_urls", None))
    primary = str(getattr(generation, "result_url", "") or "").strip()
    return list(dict.fromkeys([*urls, *([primary] if primary else [])]))


def generation_display_result_urls(generation: Any) -> list[str]:
    urls = [url for url in _json_url_list(getattr(generation, "result_urls", None)) if public_url_is_available(url)]
    primary = str(getattr(generation, "result_url", "") or "").strip()
    return urls or ([primary] if primary and public_url_is_available(primary) else [])


def feed_source_output_id(source: Any, url: str) -> str:
    """Opaque consistency binding, never authorization or an input-photo identifier."""
    identity = json.dumps([getattr(source, "id", None), url], separators=(",", ":"))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def is_feed_source_alias(source: Any, url: str) -> bool:
    """Recognize this source's trusted viewer path even with an invalid query.

    Recognition only excludes/rejects scene aliases; it never authorizes them.
    """
    source_type = getattr(getattr(source, "gen_type", None), "value", getattr(source, "gen_type", None))
    if source_type != "image":
        return False
    try:
        parsed = urlparse(url)
        public_base = urlparse(str(getattr(settings, "WEB_PUBLIC_URL", "") or ""))
        parsed_port, public_port = parsed.port, public_base.port
    except ValueError:
        return False
    if (
        parsed.scheme.lower() != public_base.scheme.lower()
        or parsed.hostname != public_base.hostname or parsed_port != public_port
        or parsed.username is not None or parsed.password is not None
    ):
        return False
    match = re.fullmatch(r"/api/v1/feed/(\d+)/(?:preview|display)\.webp", parsed.path)
    try:
        return match is not None and int(match.group(1)) == getattr(source, "id", None)
    except ValueError:
        return False


def _feed_source_alias_parts(source: Any, url: str) -> tuple[int, str | None] | None:
    if not is_feed_source_alias(source, url):
        return None
    parsed = urlparse(url)
    if parsed.fragment:
        return None
    query = parse_qs(parsed.query, keep_blank_values=True)
    if set(query) not in ({"index"}, {"index", "output_id"}) or len(query["index"]) != 1:
        return None
    output_ids = query.get("output_id")
    if output_ids is not None and (len(output_ids) != 1 or re.fullmatch(r"[a-f0-9]{64}", output_ids[0]) is None):
        return None
    try:
        index = int(query["index"][0])
    except ValueError:
        return None
    if index < 0 or index >= 4:
        return None
    return index, output_ids[0] if output_ids else None


def _feed_source_alias_index(source: Any, url: str) -> int | None:
    parts = _feed_source_alias_parts(source, url)
    return parts[0] if parts is not None else None


def canonical_feed_source_reference(source: Any, url: str, source_urls: list[str] | None = None) -> str:
    """Resolve only server-known preview/display aliases of this exact source."""
    source_urls = generation_display_result_urls(source) if source_urls is None else source_urls
    parts = _feed_source_alias_parts(source, url)
    if parts is None:
        return url
    index, output_id = parts
    if output_id is not None:
        return next((candidate for candidate in source_urls if feed_source_output_id(source, candidate) == output_id), url)
    return source_urls[index] if index < len(source_urls) else url


def validated_feed_source_reference(source: Any, url: str, source_urls: list[str]) -> str:
    """Paid launches accept only an available exact output or a bound server alias.

    Legacy index aliases cannot prove which scene was saved before a payment or
    reload. Require a fresh gallery selection instead of silently rebinding them.
    """
    if url in source_urls:
        return url
    parts = _feed_source_alias_parts(source, url)
    if parts is not None and parts[1] is not None:
        canonical = canonical_feed_source_reference(source, url, source_urls)
        if canonical in source_urls:
            return canonical
    raise ValueError("Unavailable or unbound feed scene")


def feed_identity_references(source: Any, requested_refs: list[str]) -> list[str]:
    """Exclude all this source's outputs/aliases before assigning identity roles."""
    known = set(generation_result_reference_urls(source))
    return list(dict.fromkeys(
        url.strip() for url in requested_refs
        if isinstance(url, str) and url.strip()
        and url.strip() not in known and not is_feed_source_alias(source, url.strip())
    ))


def selected_feed_source_url(source: Any, requested_refs: list[str]) -> str | None:
    """Resolve the selected scene regardless of historical reference order."""
    known = generation_result_reference_urls(source)
    for url in reversed(requested_refs):
        if not isinstance(url, str):
            continue
        index = _feed_source_alias_index(source, url.strip())
        parts = _feed_source_alias_parts(source, url.strip())
        if parts is None and is_feed_source_alias(source, url.strip()):
            return None
        if parts is not None and parts[1] is not None:
            canonical = canonical_feed_source_reference(source, url.strip())
            return canonical if canonical in generation_display_result_urls(source) else None
        if index is not None:
            stored_gallery = _json_url_list(getattr(source, "result_urls", None))
            if stored_gallery and generation_display_result_urls(source) != stored_gallery:
                # Old snapshots kept a display index, not an immutable result URL.
                # Expiry can shift that index; guessing would silently change scenes.
                return None
        canonical = canonical_feed_source_reference(source, url.strip())
        if canonical in known:
            return canonical
        if index is not None and index < len(known):
            return known[index]
    return canonical_generation_result_url(source)
