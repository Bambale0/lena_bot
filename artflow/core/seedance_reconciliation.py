"""Per-generation unknown-video state and legacy diagnostic incident markers.

The Redis/DB review markers are internal telemetry only. New paid submissions
never consult them for provider routing; a separate scheduler expires each old
generation individually using guarded refunds. No second paid POST is issued.
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
    """Legacy incident-state diagnostic; not used to route new paid requests."""
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
    """Record a bounded diagnostic marker for the ambiguous provider request."""
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
    """Legacy diagnostic query, not an admission gate for other users."""
    from sqlalchemy import or_, select

    from db.models import Generation, GenerationStatus, GenerationType
    from db.session import AsyncSessionLocal

    review_marker = (
        r'"neironych_video_reconciliation"\s*:\s*\{[^}]*'
        # PostgreSQL ARE uses \b for backspace, not a word boundary (PR205).
        r'"required"\s*:\s*true\s*[,}]'
    )
    query = select(select(Generation.id).where(
        Generation.model == product_model,
        Generation.gen_type == GenerationType.video,
        Generation.status.in_([GenerationStatus.pending, GenerationStatus.processing]),
        or_(Generation.task_id.like("neironych:%"), Generation.task_id.like("web:neironych:%"),
            Generation.task_id.like("neironych-submit:%"), Generation.task_id.like("web:neironych-submit:%")),
        Generation.input_params.op("~")(review_marker),
    ).exists())
    async with AsyncSessionLocal() as session:
        return bool(await session.scalar(query))


def make_submission_context(session, gen_id: int, product_model: str, *, surface: str = "miniapp"):
    """Allocate only a NEW attempt; the callback is a durable one-shot gate."""
    from uuid import uuid4

    from api.neironych_seedance import NeironychSubmissionUnknown
    from api.neironych_seedance_runtime import SubmissionContext
    from db import repository as repo

    if product_model not in PRODUCT_MODELS:
        return None
    request_id = str(uuid4())

    async def before_submit(idempotency_key: str, payload_sha256: str) -> None:
        if context.started or not await repo.begin_seedance_submission(
            session, gen_id, request_id, idempotency_key, payload_sha256,
            product_model=product_model, surface=surface,
        ):
            raise NeironychSubmissionUnknown(request_id, idempotency_key)
        context.started = True

    context = SubmissionContext(client_request_id=request_id, before_submit=before_submit)
    return context


async def handle_submission_unknown(session, gen_id: int, context) -> bool:
    from db import repository as repo

    if context is None:
        return False
    # A previous commit failure leaves SQLAlchemy unusable until rollback.
    if callable(getattr(session, "rollback", None)):
        await session.rollback()
    changed = await repo.mark_seedance_submission_unknown(session, gen_id, context.client_request_id)
    if changed:
        gen = await repo.get_generation_by_id(session, gen_id)
        try:
            await pause_neironych_route(gen.model, context.client_request_id)
        except Exception:
            logger.warning("Seedance admission cache unavailable gen=%s", gen_id)
    return changed


async def persist_submission_result(session, gen_id: int, context, task_id: str, *, surface: str = "miniapp") -> bool:
    from db import repository as repo
    from db.models import GenerationStatus

    if surface == "web" and not task_id.startswith("web:"):
        task_id = "web:" + task_id
    if context is not None and context.started:
        return await repo.bind_seedance_submission_task(session, gen_id, context.client_request_id, task_id)
    # A KIE-primary success did not run the pre-POST callback. Still refuse
    # superseded/terminal rows under the same lock as submission admission.
    gen = await repo._locked_seedance_generation(session, gen_id)
    if (gen is None or gen.status not in (GenerationStatus.pending, GenerationStatus.processing)
            or gen.task_id or repo.parse_input_params(gen.input_params).get(repo.SEEDANCE_SUBMISSION_KEY)):
        await session.commit()
        return False
    gen.task_id = task_id
    gen.status = GenerationStatus.processing
    await session.commit()
    await repo._publish_generation_update(gen)
    return True


async def recover_submission_identity(session, gen):
    """Read-only provider discovery; never resubmit/refund a missing response."""
    import asyncio

    from api.neironych_seedance_runtime import lookup_submission
    from db import repository as repo

    task_id = str(gen.task_id or "")
    if not task_id.startswith(repo.SEEDANCE_SUBMISSION_PREFIXES):
        return gen
    params = repo.parse_input_params(gen.input_params)
    marker = params.get(repo.SEEDANCE_SUBMISSION_KEY)
    if not isinstance(marker, dict):
        return gen
    request_id = marker.get("client_request_id")
    if (not isinstance(request_id, str) or task_id not in (
            "neironych-submit:" + request_id, "web:neironych-submit:" + request_id)
            or marker.get("product_model") != gen.model or not marker.get("idempotency_key")):
        return gen
    # Snapshot identity before releasing the connection for the provider GET.
    model, key, gen_id = gen.model, marker["idempotency_key"], gen.id
    await session.commit()
    provider_id = None
    try:
        provider_id = await asyncio.wait_for(
            lookup_submission(request_id, product_model=model, idempotency_key=key),
            timeout=settings.NEIRONYCH_VIDEO_RECONCILE_TIMEOUT_SECONDS,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Seedance submission lookup delayed gen=%s error=%s", gen_id, type(exc).__name__)
    if provider_id:
        bound_task = ("web:" if task_id.startswith("web:") else "") + "neironych:" + provider_id
        await repo.bind_seedance_submission_task(session, gen_id, request_id, bound_task)
    else:
        changed = await repo.mark_seedance_submission_unknown(session, gen_id, request_id)
        if changed:
            try:
                await pause_neironych_route(model, request_id)
            except Exception:
                logger.warning("Seedance admission cache unavailable gen=%s", gen_id)
    return await repo.get_generation_by_id(session, gen_id) or gen


async def handle_submission_not_sent(session, gen_id: int, context) -> bool:
    """Refund only a proven pre-POST failure, with the identity lock retained."""
    from db import repository as repo
    from db.models import GenerationStatus

    if context is None or context.started:
        return False
    if callable(getattr(session, "rollback", None)):
        await session.rollback()
    gen = await repo._locked_seedance_generation(session, gen_id)
    if gen is None or gen.status not in (GenerationStatus.pending, GenerationStatus.processing):
        await session.commit()
        return False
    params = repo.parse_input_params(gen.input_params)
    marker = params.get(repo.SEEDANCE_SUBMISSION_KEY)
    untouched = not gen.task_id and not marker
    same_attempt = repo._active_seedance_submission(gen, context.client_request_id) is not None
    if not untouched and not same_attempt:
        await session.commit()
        return False
    # No commit between the CAS check and atomic failed+ledger+balance update.
    failed, _ = await repo.fail_generation_and_refund(
        session, gen_id, "Video was not submitted: launch record could not be persisted",
        refund_note="Seedance pre-submit persistence failure",
        expected_task_id=gen.task_id,
    )
    return failed
