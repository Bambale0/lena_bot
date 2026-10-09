"""Nonterminal video review state and model-scoped admission circuit.

The circuit changes only NEW submissions. It never retries or refunds an
already-paid ambiguous request. PostgreSQL remains the source of job state.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from core.config import settings

logger = logging.getLogger(__name__)
RECONCILIATION_KEY = "neironych_video_reconciliation"
PUBLIC_REVIEW_STATUS = "reconciliation_required"
PRODUCT_MODELS = frozenset({"bytedance/seedance-2", "bytedance/seedance-2-5"})


def public_generation_status(gen: Any) -> str:
    status = str(getattr(gen.status, "value", gen.status))
    if status not in {"pending", "processing"}:
        return status
    if str(getattr(gen, "model", "")) not in PRODUCT_MODELS:
        return status
    try:
        params = json.loads(getattr(gen, "input_params", None) or "{}")
    except (TypeError, ValueError):
        return status
    marker = params.get(RECONCILIATION_KEY) if isinstance(params, dict) else None
    if isinstance(marker, dict) and marker.get("required") is True:
        return PUBLIC_REVIEW_STATUS
    return status


def _circuit_key(product_model: str) -> str:
    if product_model not in PRODUCT_MODELS:
        raise ValueError("Unsupported Seedance product model")
    env = str(settings.ENV or "development").strip().lower()
    return f"apix:seedance-uncertain-admission:{env}:{product_model}"


def _redis_client():
    return aioredis.Redis.from_url(
        settings.REDIS_URL, decode_responses=True,
        socket_connect_timeout=1.5, socket_timeout=2.0,
    )


async def neironych_route_paused(product_model: str) -> bool:
    """Check before any provider POST; fail closed on inaccessible coordinator."""
    key = _circuit_key(product_model)
    client = _redis_client()
    try:
        if await client.exists(key):
            return True
    finally:
        await client.aclose()
    # The review marker was committed before the best-effort Redis pause.
    # A missing/expired/lost cache key must not reopen that known-bad route.
    return await _db_has_unresolved_seedance(product_model)


async def pause_neironych_route(product_model: str, request_id: str) -> None:
    """Refresh a bounded circuit while explicit unresolved submissions persist."""
    key = _circuit_key(product_model)
    client = _redis_client()
    try:
        await client.set(
            key, json.dumps({"reason": "submission_outcome_unknown", "request_id": request_id}),
            ex=settings.SEEDANCE_UNCERTAIN_ROUTE_COOLDOWN_SECONDS,
        )
    finally:
        await client.aclose()


async def _db_has_unresolved_seedance(product_model: str) -> bool:
    """Authoritative admission fallback; never send paid work on a DB failure."""
    from sqlalchemy import or_, select

    from db.models import Generation, GenerationStatus, GenerationType
    from db.session import AsyncSessionLocal

    review_marker = (
        r'"neironych_video_reconciliation"\s*:\s*\{[^}]*'
        # PostgreSQL ARE uses \b for backspace, not Python's word boundary.
        # A JSON boolean is followed by whitespace and a comma or closing brace.
        r'"required"\s*:\s*true\s*[,}]'
    )
    query = select(select(Generation.id).where(
        Generation.model == product_model,
        Generation.gen_type == GenerationType.video,
        Generation.status.in_([GenerationStatus.pending, GenerationStatus.processing]),
        or_(Generation.task_id.like("neironych:%"), Generation.task_id.like("web:neironych:%")),
        Generation.input_params.op("~")(review_marker),
    ).exists())
    async with AsyncSessionLocal() as session:
        return bool(await session.scalar(query))
