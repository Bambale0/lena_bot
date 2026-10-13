from __future__ import annotations

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


def _feed_source_alias_index(source: Any, url: str) -> int | None:
    """Recognize scene aliases even when a saved gallery output has expired."""
    source_type = getattr(getattr(source, "gen_type", None), "value", getattr(source, "gen_type", None))
    if source_type != "image":
        return None
    parsed = urlparse(url)
    public_base = urlparse(str(getattr(settings, "WEB_PUBLIC_URL", "") or ""))
    try:
        parsed_port, public_port = parsed.port, public_base.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() != public_base.scheme.lower()
        or parsed.hostname != public_base.hostname or parsed_port != public_port
        or parsed.username is not None or parsed.password is not None or parsed.fragment
    ):
        return None
    match = re.fullmatch(r"/api/v1/feed/(\d+)/(?:preview|display)\.webp", parsed.path)
    if match is None:
        return None
    query = parse_qs(parsed.query, keep_blank_values=True)
    if set(query) != {"index"} or len(query["index"]) != 1:
        return None
    try:
        source_id, index = int(match.group(1)), int(query["index"][0])
    except ValueError:
        return None
    if source_id != getattr(source, "id", None) or index < 0 or index >= 4:
        return None
    return index


def canonical_feed_source_reference(source: Any, url: str, source_urls: list[str] | None = None) -> str:
    """Resolve only server-known preview/display aliases of this exact source."""
    source_urls = generation_display_result_urls(source) if source_urls is None else source_urls
    index = _feed_source_alias_index(source, url)
    return source_urls[index] if index is not None and index < len(source_urls) else url


def feed_identity_references(source: Any, requested_refs: list[str]) -> list[str]:
    """Exclude all this source's outputs/aliases before assigning identity roles."""
    known = set(generation_result_reference_urls(source))
    return list(dict.fromkeys(
        url.strip() for url in requested_refs
        if isinstance(url, str) and url.strip()
        and url.strip() not in known and _feed_source_alias_index(source, url.strip()) is None
    ))


def selected_feed_source_url(source: Any, requested_refs: list[str]) -> str | None:
    """Keep the selected scene stored last by the server in personalized repeats."""
    known = generation_result_reference_urls(source)
    for url in reversed(requested_refs):
        if not isinstance(url, str):
            continue
        index = _feed_source_alias_index(source, url.strip())
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
