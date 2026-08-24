from __future__ import annotations

import json
from typing import Any

from api.public_files import public_url_is_available


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
