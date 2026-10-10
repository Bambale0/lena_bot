"""Fair, bounded background recovery for Neironych Seedance 2/2.5 videos.

The provider GET and eventual media download never submit another paid POST.
DB transitions and Telegram notice claims remain guarded by repository locks.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from sqlalchemy import DateTime, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from api import neironych_seedance_runtime
from api.neironych_seedance_runtime import PRODUCT_MODELS
from core.admin_alerts import send_admin_alert_once
from core.config import settings
from core.neironych_video_poll_gate import (
    neironych_video_poll_guard,
    protect_neironych_video_poll_settlement,
)
from db import repository as repo
from db.models import Generation, GenerationStatus, GenerationType
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

_PROVIDER_REVIEW_PENDING_REGEX = (
    r'"seedance_refund_provider_review"\s*:\s*\{[^}]*"state"\s*:\s*"pending"'
)

_NOTICE_PENDING_REGEX = (
    r'"neironych_video_notice"\s*:\s*\{[^}]*"state"\s*:\s*"(pending|sending)"'
)

_TRACK_NOTICES_AND_CHECKPOINT_LUA = """
-- An old notice MUST be in the retry queue before the sweep cursor advances.
-- This Lua transaction cannot leave a persisted checkpoint without its IDs.
for i = 3, #ARGV do
    redis.call('ZADD', KEYS[2], 'NX', ARGV[2], ARGV[i])
end
redis.call('SET', KEYS[1], ARGV[1])
return 1
"""


@dataclass
class _ScanCursor:
    newest_id: int = 0
    older_id: int = 0
    older_ceiling: int = 0
    single_old_next: bool = False


_video_cursor = _ScanCursor()
_notice_cursor = _ScanCursor()
_refund_review_cursor = _ScanCursor()
_last_overdue_warning: dict[int, datetime] = {}
_last_missing_id_warning: datetime | None = None


def _eligible_video_query():
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=settings.NEIRONYCH_VIDEO_RECONCILE_MIN_AGE_SECONDS
    )
    return select(Generation.id).where(
        Generation.gen_type == GenerationType.video,
        Generation.model.in_(tuple(PRODUCT_MODELS)),
        Generation.status.in_((GenerationStatus.pending, GenerationStatus.processing)),
        or_(
            Generation.task_id.like("neironych:%"),
            Generation.task_id.like("web:neironych:%"),
            Generation.task_id.like("neironych-submit:%"),
            Generation.task_id.like("web:neironych-submit:%"),
        ),
        Generation.created_at <= cutoff,
    )


# A timeout is about a *single paid task*, not a global model circuit. The
# deadline includes both bound and unbound persisted Neironych submissions.
_NEIRONYCH_TASK_PREFIXES = (
    "neironych:", "web:neironych:",
    "neironych-submit:", "web:neironych-submit:",
    "kie-submit:", "web:kie-submit:",
)


def _seedance_started_at(gen: Generation) -> datetime:
    """Refund timer is anchored to persisted paid submission, not preparation."""
    params = repo.parse_input_params(getattr(gen, "input_params", None))
    task = str(getattr(gen, "task_id", "") or "").removeprefix("web:")
    marker = params.get(repo.KIE_VIDEO_SUBMISSION_KEY) if task.startswith(
        "kie-submit:"
    ) else params.get(repo.SEEDANCE_SUBMISSION_KEY)
    stamp = marker.get("started_at") if isinstance(marker, dict) else None
    if isinstance(stamp, str):
        try:
            value = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if value.tzinfo is not None:
                return value.astimezone(timezone.utc)
        except ValueError:
            pass
    created = gen.created_at
    return created if created.tzinfo else created.replace(tzinfo=timezone.utc)


def _expired_seedance_query():
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=settings.SEEDANCE_AUTO_REFUND_SECONDS
    )
    params_json = cast(Generation.input_params, JSONB)
    neironych_started = func.jsonb_extract_path_text(
        params_json, repo.SEEDANCE_SUBMISSION_KEY, "started_at"
    )
    kie_started = func.jsonb_extract_path_text(
        params_json, repo.KIE_VIDEO_SUBMISSION_KEY, "started_at"
    )
    started = func.coalesce(
        cast(kie_started, DateTime(timezone=True)),
        cast(neironych_started, DateTime(timezone=True)),
        Generation.created_at,
    )
    return select(Generation.id).where(
        Generation.gen_type == GenerationType.video,
        Generation.model.in_(tuple(PRODUCT_MODELS)),
        Generation.status.in_((GenerationStatus.pending, GenerationStatus.processing)),
        or_(*(Generation.task_id.like(prefix + "%")
              for prefix in _NEIRONYCH_TASK_PREFIXES)),
        started <= cutoff,
    )


async def _load_expired_seedance_batch() -> list[int]:
    # Oldest-first, bounded and self-draining: terminal rows disappear from
    # this query. It must not depend on Redis notice queues or provider health.
    async with AsyncSessionLocal() as session:
        ids = list((await session.execute(
            _expired_seedance_query()
            .order_by(Generation.created_at.asc(), Generation.id.asc())
            .limit(settings.NEIRONYCH_VIDEO_RECONCILE_BATCH_SIZE)
        )).scalars().all())
        await session.rollback()
    return ids


async def _final_neironych_provider_status(gen: Generation) -> tuple[str, str | None]:
    """One bounded GET only: completed, failed, pending, unknown or newly bound."""
    task = str(gen.task_id or "").removeprefix("web:")
    if task.startswith("kie-submit:"):
        # Kie has not supplied a task ID, so no canonical GET is available.
        # A signed webhook can still bind the original paid order later.
        return "unknown", None
    if task.startswith("neironych-submit:"):
        marker = repo.parse_input_params(gen.input_params).get(repo.SEEDANCE_SUBMISSION_KEY)
        if not isinstance(marker, dict) or not marker.get("idempotency_key"):
            return "unknown", None
        provider_id = await asyncio.wait_for(
            neironych_seedance_runtime.lookup_submission(
                marker["client_request_id"], product_model=gen.model,
                idempotency_key=marker["idempotency_key"],
            ), timeout=settings.SEEDANCE_FINAL_STATUS_TIMEOUT_SECONDS,
        )
        return ("bound", str(provider_id)) if provider_id else ("unknown", None)
    if not neironych_seedance_runtime.is_task_id(task):
        return "unknown", None
    client = neironych_seedance_runtime._client()
    try:
        remote = await asyncio.wait_for(
            client.get_video(neironych_seedance_runtime.decode_task_id(task)),
            timeout=settings.SEEDANCE_FINAL_STATUS_TIMEOUT_SECONDS,
        )
    finally:
        await client.aclose()
    if remote.done:
        return "done", None
    if remote.failed:
        return "failed", None
    return "pending", None


async def _settle_expired_seedance(
    gen_id: int, task_id: str, remote_state: str,
) -> bool:
    now = datetime.now(timezone.utc)
    review: dict[str, object] | None = None
    if remote_state != "failed":
        # Atomic with the refund; still exists after an app restart.
        review = {
            "state": "pending", "reason": "timeout_provider_unconfirmed",
            "original_task_id": task_id,
            "refunded_at": now.isoformat(),
            "next_check_at": now.isoformat(),
            "last_provider_status": remote_state,
            "checks": 0,
        }
    async with AsyncSessionLocal() as session:
        gen = await repo.get_generation_by_id(session, gen_id)
        if (gen is None or gen.status not in (
                GenerationStatus.pending, GenerationStatus.processing)
                or str(gen.task_id or "") != task_id):
            return False
        if ((datetime.now(timezone.utc) - _seedance_started_at(gen)).total_seconds()
                < settings.SEEDANCE_AUTO_REFUND_SECONDS):
            return False
        # The Redis lease may be lost after the DB settlement has begun.
        protect_neironych_video_poll_settlement()
        telegram = task_id.startswith(("neironych:", "neironych-submit:", "kie-submit:"))
        changed, credits = await repo.fail_generation_and_refund(
            session, gen_id, "Видео не удалось создать вовремя.",
            expected_task_id=task_id,
            refund_note=("seedance:auto_timeout:provider_failed" if remote_state == "failed"
                         else "seedance:auto_timeout:provider_review_pending"),
            video_notice_kind="failed" if telegram else None,
            provider_review=review,
        )
    if changed:
        logger.warning(
            "Seedance auto-timeout gen=%s remote=%s refunded=%s review_pending=%s",
            gen_id, remote_state, credits, bool(review),
        )
        if telegram:
            try:
                await _track_active_video_notice_intent(gen_id)
            except Exception as exc:
                logger.warning(
                    "Seedance timeout notice retry deferred gen=%s error=%s",
                    gen_id, type(exc).__name__,
                )
    return changed


def _provider_refund_review_query():
    """Durable audit lane for paid upstream tasks after customer refunds."""
    return select(Generation.id).where(
        Generation.gen_type == GenerationType.video,
        Generation.model.in_(tuple(PRODUCT_MODELS)),
        Generation.status == GenerationStatus.failed,
        Generation.input_params.op("~")(_PROVIDER_REVIEW_PENDING_REGEX),
    )


async def _expire_stuck_seedance_video(gen_id: int) -> bool:
    """Use the same per-provider-task lock as ordinary media delivery."""
    async with AsyncSessionLocal() as session:
        gen = await repo.get_generation_by_id(session, gen_id)
        if (gen is None or gen.status not in (
                GenerationStatus.pending, GenerationStatus.processing)
                or gen.gen_type != GenerationType.video
                or gen.model not in PRODUCT_MODELS):
            return False
        task_id = str(gen.task_id or "")
        if not task_id.startswith(_NEIRONYCH_TASK_PREFIXES):
            return False
        if ((datetime.now(timezone.utc) - _seedance_started_at(gen)).total_seconds()
                < settings.SEEDANCE_AUTO_REFUND_SECONDS):
            return False
        await session.rollback()

    # A completed video being downloaded elsewhere owns this same key.
    async with neironych_video_poll_guard(task_id.removeprefix("web:")) as claimed:
        if not claimed:
            logger.info("Seedance timeout deferred, poll already owns gen=%s", gen_id)
            return False
        async with AsyncSessionLocal() as session:
            current = await repo.get_generation_by_id(session, gen_id)
            if (current is None or current.status not in (
                    GenerationStatus.pending, GenerationStatus.processing)
                    or str(current.task_id or "") != task_id):
                return False
            if ((datetime.now(timezone.utc) - _seedance_started_at(current)).total_seconds()
                    < settings.SEEDANCE_AUTO_REFUND_SECONDS):
                return False
            await session.rollback()

        remote_state = "unknown"
        provider_id = None
        try:
            remote_state, provider_id = await _final_neironych_provider_status(current)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Seedance final status deferred gen=%s reason=%s",
                gen_id, type(exc).__name__,
            )

        if remote_state == "done":
            # Completion with temporarily failed media retrieval is NOT a
            # supplier failure. Defer compensation and retry delivery.
            return False
        if remote_state == "bound" and provider_id:
            async with AsyncSessionLocal() as session:
                marker = repo.parse_input_params(current.input_params).get(
                    repo.SEEDANCE_SUBMISSION_KEY
                )
                if isinstance(marker, dict):
                    task = ("web:" if task_id.startswith("web:") else "")
                    await repo.bind_seedance_submission_task(
                        session, gen_id, marker["client_request_id"],
                        task + "neironych:" + provider_id,
                    )
            return False
        return await _settle_expired_seedance(gen_id, task_id, remote_state)


async def _review_refunded_provider_task(gen_id: int) -> bool:
    """Continue read-only supplier reconciliation after customer settlement.

    The customer is already final/refunded. Late completion updates only this
    internal supplier audit marker, never the customer's wallet or video state.
    """
    async with AsyncSessionLocal() as session:
        gen = await repo.get_generation_by_id(session, gen_id)
        if gen is None or gen.status != GenerationStatus.failed:
            return False
        review = repo.parse_input_params(gen.input_params).get(
            repo.SEEDANCE_REFUND_PROVIDER_REVIEW_KEY
        )
        if not isinstance(review, dict) or review.get("state") != "pending":
            return False
        due = repo._notice_timestamp(review.get("next_check_at"))
        if due is not None and due > datetime.now(timezone.utc):
            return False
        task = str(review.get("original_task_id") or gen.task_id or "")
        previous_bound = str(review.get("provider_task_id") or "")
        model = gen.model
        params = gen.input_params
        await session.rollback()

    # The provider may discover a previously unbound submission much later.
    from types import SimpleNamespace
    if previous_bound:
        task = ("web:" if task.startswith("web:") else "") + "neironych:" + previous_bound
    shadow = SimpleNamespace(task_id=task, model=model, input_params=params)
    status = "unknown"
    discovered_id: str | None = None
    try:
        status, discovered_id = await _final_neironych_provider_status(shadow)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Seedance refunded supplier review delayed gen=%s error=%s",
            gen_id, type(exc).__name__,
        )

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        locked = (await session.execute(
            select(Generation).where(Generation.id == gen_id).with_for_update()
            .execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if locked is None or locked.status != GenerationStatus.failed:
            await session.rollback()
            return False
        metadata = repo.parse_input_params(locked.input_params)
        marker = metadata.get(repo.SEEDANCE_REFUND_PROVIDER_REVIEW_KEY)
        if not isinstance(marker, dict) or marker.get("state") != "pending":
            await session.rollback()
            return False
        marker["checks"] = int(marker.get("checks") or 0) + 1
        marker["last_checked_at"] = now.isoformat()
        marker["last_provider_status"] = status
        marker["next_check_at"] = (
            now + timedelta(seconds=settings.SEEDANCE_PROVIDER_REFUND_REVIEW_INTERVAL_SECONDS)
        ).isoformat()
        if discovered_id:
            marker["provider_task_id"] = discovered_id
        if status == "done":
            marker["state"] = "remote_completed_pending_finance"
            marker["reconciled_at"] = now.isoformat()
        elif status == "failed":
            marker["state"] = "remote_failed"
            marker["reconciled_at"] = now.isoformat()
        # Unknown forever is not a silent lifetime block. Escalate after
        # bounded checks, keep the account protected until an authorized
        # operator confirms that the supplier liability is settled.
        if (status in ("unknown", "pending") and
                (int(marker["checks"]) >= settings.SEEDANCE_PROVIDER_REFUND_MAX_CHECKS or
                 (now - repo._notice_timestamp(marker.get("refunded_at")) if
                  repo._notice_timestamp(marker.get("refunded_at")) else timedelta()).total_seconds()
                 >= settings.SEEDANCE_PROVIDER_REFUND_MAX_REVIEW_SECONDS)):
            marker["state"] = "needs_admin_resolution"
            marker["escalated_at"] = now.isoformat()
        metadata[repo.SEEDANCE_REFUND_PROVIDER_REVIEW_KEY] = marker
        locked.input_params = json.dumps(metadata, ensure_ascii=False)
        await session.commit()
    if status in ("done", "failed") or marker.get("state") == "needs_admin_resolution":
        logger.warning(
            "Seedance refunded provider task resolved or escalated gen=%s remote=%s; "
            "customer_final_state_unchanged=true", gen_id, status,
        )
        try:
            await send_admin_alert_once(
                alert_key=f"seedance-late-provider-result:{gen_id}:{status}",
                title="Seedance: подтверждён исход после возврата",
                message=f"APIX задача {gen_id}; Нейроныч статус {status}. "
                        "Если задача не подтверждена или результат опоздал, проверьте закупочный расход и "
                        "завершите сверку в защищённом admin API. Баланс пользователя не менялся.",
            )
        except Exception as exc:
            logger.warning("Seedance supplier alert deferred gen=%s error=%s",gen_id,type(exc).__name__)
    return True


def _eligible_notice_query():
    return select(Generation.id).where(
        Generation.gen_type == GenerationType.video,
        Generation.model.in_(tuple(PRODUCT_MODELS)),
        Generation.status.in_((GenerationStatus.done, GenerationStatus.failed)),
        or_(
            Generation.task_id.like("neironych:%"),
            Generation.task_id.like("neironych-submit:%"),
            Generation.task_id.like("kie-submit:%"),
        ),
        Generation.input_params.op("~")(_NOTICE_PENDING_REGEX),
    )


async def _pick_ids(session, query, cursor: _ScanCursor, limit: int) -> list[int]:
    """Reserve fresh + revisit lanes so old jobs cannot starve under new traffic."""
    if cursor.newest_id == 0:
        initial = list((await session.execute(
            query.order_by(Generation.id.asc()).limit(limit)
        )).scalars().all())
        if initial:
            cursor.newest_id = max(initial)
        return initial

    if limit == 1:
        forward_limit = 0 if cursor.single_old_next else 1
        cursor.single_old_next = not cursor.single_old_next
    else:
        forward_limit = max(1, limit // 2)
    revisit_limit = limit - forward_limit

    current_ceiling = cursor.newest_id
    fresh: list[int] = []
    if forward_limit:
        fresh = list((await session.execute(
            query.where(Generation.id > cursor.newest_id)
            .order_by(Generation.id.asc()).limit(forward_limit)
        )).scalars().all())
        if fresh:
            cursor.newest_id = fresh[-1]

    revisit_limit += forward_limit - len(fresh)
    if revisit_limit:
        if not cursor.older_ceiling:
            cursor.older_ceiling = current_ceiling
            cursor.older_id = 0
        older = list((await session.execute(
            query.where(
                Generation.id > cursor.older_id,
                Generation.id <= cursor.older_ceiling,
            ).order_by(Generation.id.asc()).limit(revisit_limit)
        )).scalars().all())
        if not older:
            # Complete the bounded old-row sweep; start a new one at the next
            # maximum, never resetting only to the oldest permanent stuck ID.
            cursor.older_ceiling = cursor.newest_id
            cursor.older_id = 0
            older = list((await session.execute(
                query.where(Generation.id <= cursor.older_ceiling)
                .order_by(Generation.id.asc()).limit(revisit_limit)
            )).scalars().all())
        if older:
            cursor.older_id = older[-1]
            if cursor.older_id >= cursor.older_ceiling:
                cursor.older_ceiling = 0
                cursor.older_id = 0
        fresh.extend(row_id for row_id in older if row_id not in fresh)

    return fresh[:limit]


async def _load_batch(query, cursor: _ScanCursor) -> list[int]:
    async with AsyncSessionLocal() as session:
        ids = await _pick_ids(
            session, query, cursor, settings.NEIRONYCH_VIDEO_RECONCILE_BATCH_SIZE,
        )
        await session.rollback()  # Release read-only transaction before HTTP calls.
    return ids



def _notice_checkpoint_key() -> str:
    env = str(settings.ENV or "development").strip().lower()
    return f"apix:neironych-video-notice-sweep:{env}:last-id"


def _notice_retry_queue_key() -> str:
    return _notice_checkpoint_key() + ":retry-due"


def _notice_redis_client():
    return aioredis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=1.5,
        socket_timeout=2.0,
        health_check_interval=30,
        max_connections=3,
    )


async def _load_notice_batch() -> list[int]:
    """Discover notices by ID and preserve pending retry IDs across restarts.

    Lua atomically records all discovered IDs in the durable Redis sorted set
    before advancing the historical cursor. Failed sends and unexpired leases
    stay in the sorted set until their next due time, without another DB sweep.
    """
    client = _notice_redis_client()
    try:
        checkpoint_key = _notice_checkpoint_key()
        queue_key = _notice_retry_queue_key()
        stored = await client.get(checkpoint_key)
        _notice_cursor.older_id = max(0, int(stored or 0))
        ids = await _load_notice_batch_at_cursor()
        now = datetime.now(timezone.utc).timestamp()
        await client.eval(
            _TRACK_NOTICES_AND_CHECKPOINT_LUA,
            2,
            checkpoint_key,
            queue_key,
            str(_notice_cursor.older_id),
            str(now),
            *(str(gen_id) for gen_id in ids),
        )
        due_ids = await client.zrangebyscore(
            queue_key, "-inf", now,
            start=0, num=settings.NEIRONYCH_VIDEO_RECONCILE_BATCH_SIZE,
        )
        return list(dict.fromkeys(int(gen_id) for gen_id in due_ids))
    finally:
        await client.aclose()


async def _load_notice_batch_at_cursor() -> list[int]:
    """Bound regex work to indexed primary-key windows, even when outbox is empty.

    The recent lane notices new finished videos promptly; the sweep lane
    eventually covers old undelivered receipts after outages/restarts.
    Neither lane scans the entire historical Text column on every tick.
    """
    size = settings.NEIRONYCH_VIDEO_RECONCILE_BATCH_SIZE
    span = settings.NEIRONYCH_VIDEO_NOTICE_SCAN_ID_SPAN
    if size == 1:
        recent_limit = 0 if _notice_cursor.single_old_next else 1
        _notice_cursor.single_old_next = not _notice_cursor.single_old_next
    else:
        recent_limit = max(1, size // 2)
    sweep_limit = size - recent_limit

    async with AsyncSessionLocal() as session:
        max_id = int(await session.scalar(select(func.max(Generation.id))) or 0)
        if max_id <= 0:
            await session.rollback()
            return []

        candidates = _eligible_notice_query()
        recent_ids: list[int] = []
        if recent_limit:
            recent_start = max(0, max_id - span)
            recent_ids = list((await session.execute(
                candidates.where(
                    Generation.id > recent_start,
                    Generation.id <= max_id,
                ).order_by(Generation.id.desc()).limit(recent_limit)
            )).scalars().all())

        sweep_ids: list[int] = []
        if sweep_limit:
            start = _notice_cursor.older_id
            if start >= max_id:
                start = 0
            ceiling = min(max_id, start + span)
            sweep_ids = list((await session.execute(
                candidates.where(
                    Generation.id > start,
                    Generation.id <= ceiling,
                ).order_by(Generation.id.asc()).limit(sweep_limit)
            )).scalars().all())
            if len(sweep_ids) >= sweep_limit:
                _notice_cursor.older_id = sweep_ids[-1]
            else:
                # Advance even when no notices match; no repeated full scan.
                _notice_cursor.older_id = 0 if ceiling >= max_id else ceiling
        await session.rollback()

    return list(dict.fromkeys([*recent_ids, *sweep_ids]))[:size]


async def _sync_notice_retry_schedule(gen_id: int) -> None:
    """Reschedule a claimed notice using the authoritative DB receipt.

    An old swept ID remains in the Redis ZSET across crashes/restarts until
    its receipt is confirmed sent/dead_letter. Never infer completion from the
    return value of a network send.
    """
    async with AsyncSessionLocal() as session:
        # One statement is one snapshot even under READ COMMITTED. Reading
        # a suppressed receipt and a later terminal status separately could
        # incorrectly erase the recovery ID just after a pending result commits.
        snapshot = (await session.execute(
            select(Generation.input_params, Generation.status).where(Generation.id == gen_id)
        )).one_or_none()
        await session.rollback()
    input_params, generation_status = snapshot if snapshot is not None else (None, None)
    params = repo.parse_input_params(input_params)
    notice = params.get(repo.NEIRONYCH_VIDEO_NOTICE_KEY)
    state = notice.get("state") if isinstance(notice, dict) else None

    now = datetime.now(timezone.utc).timestamp()
    due: float | None = None
    if state == "pending":
        scheduled = repo._notice_timestamp(notice.get("retry_at"))
        due = max(now, scheduled.timestamp()) if scheduled else now
    elif state == "sending":
        claimed = repo._notice_timestamp(notice.get("claimed_at"))
        due = (
            max(now, (claimed + timedelta(seconds=settings.NEIRONYCH_VIDEO_NOTICE_LEASE_SECONDS)).timestamp())
            if claimed else now + settings.NEIRONYCH_VIDEO_RECONCILE_INTERVAL_SECONDS
        )
    elif generation_status in (GenerationStatus.pending, GenerationStatus.processing):
        # The intent may precede finish_generation's DB commit. Do not drop
        # this old ID simply because the terminal outbox row is not ready yet.
        due = now + settings.NEIRONYCH_VIDEO_RECONCILE_INTERVAL_SECONDS

    client = _notice_redis_client()
    try:
        if due is None:
            await client.zrem(_notice_retry_queue_key(), str(gen_id))
        else:
            await client.zadd(_notice_retry_queue_key(), {str(gen_id): due})
    finally:
        await client.aclose()


async def _track_active_video_notice_intent(gen_id: int) -> None:
    """Remember an old task before it can commit a terminal Telegram notice.

    Terminal DB transition may happen far behind the notice sweep checkpoint.
    Tracking before the provider call also closes the crash window between a
    committed result and the immediate Telegram delivery attempt.
    """
    client = _notice_redis_client()
    try:
        await client.zadd(
            _notice_retry_queue_key(),
            {str(gen_id): datetime.now(timezone.utc).timestamp()
             + settings.NEIRONYCH_VIDEO_RECONCILE_INTERVAL_SECONDS},
            nx=True,
        )
    finally:
        await client.aclose()


async def _process_active_video(gen_id: int) -> bool:
    from api.miniapp_routes import _reconcile_generation_status

    async with AsyncSessionLocal() as session:
        gen = await repo.get_generation_by_id(session, gen_id)
        if gen is None or gen.status not in (GenerationStatus.pending, GenerationStatus.processing):
            return False
        task_id = str(gen.task_id or "")
        if not task_id.startswith(("neironych:", "web:neironych:", *repo.SEEDANCE_SUBMISSION_PREFIXES)):
            return False
        # Read-only ORM fields stay loaded with expire_on_commit=False. Drop
        # PostgreSQL transaction/connection before the slow provider GET or
        # potentially 250MB result download. Any terminal state re-check and
        # refund/finish acquires a fresh transaction with atomic row guards.
        await session.commit()
        if task_id.startswith(("neironych:", "neironych-submit:")):
            # If the app crashes after the terminal DB commit, this ID still
            # reaches the notice worker even when it is far behind the sweep.
            await _track_active_video_notice_intent(gen.id)
        age = (datetime.now(timezone.utc) - gen.created_at).total_seconds()
        if age >= settings.NEIRONYCH_VIDEO_ALERT_AGE_SECONDS:
            now = datetime.now(timezone.utc)
            warned_at = _last_overdue_warning.get(gen.id)
            if warned_at is None or (now - warned_at) >= timedelta(minutes=15):
                _last_overdue_warning[gen.id] = now
                logger.warning(
                    "Neironych video overdue gen=%s model=%s age_seconds=%d provider_task=%s",
                    gen.id, gen.model, age, task_id[:96],
                )
        try:
            # The provider network phase has its own wait_for budget, and
            # Telegram sends are bounded independently. An outer timeout here
            # could cancel a completed video's feed-royalty transaction *after*
            # its first commit, leaving a partial settlement forever.
            final = await _reconcile_generation_status(session, gen)
            logger.info(
                "Neironych video reconciled gen=%s model=%s status=%s age_seconds=%d",
                gen_id, gen.model, getattr(final.status, "value", final.status), age,
            )
            if final.status in (GenerationStatus.done, GenerationStatus.failed):
                _last_overdue_warning.pop(gen_id, None)
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "Neironych video reconciliation delayed gen=%s error=%s",
                gen_id, type(exc).__name__,
            )
            return False


async def _process_delivery_notice(gen_id: int) -> bool:
    from api.miniapp_routes import _deliver_pending_neironych_video_notice

    async with AsyncSessionLocal() as session:
        try:
            # The send itself has a timeout in the outbox helper. Do not
            # cancel its DB receipt transaction after Telegram accepted media.
            return await _deliver_pending_neironych_video_notice(session, gen_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "Neironych video notice recovery deferred gen=%s error=%s",
                gen_id, type(exc).__name__,
            )
            return False
        finally:
            try:
                await _sync_notice_retry_schedule(gen_id)
            except Exception:
                # A crashed/failed sync cannot remove the previously tracked
                # Redis ID; it remains due and is retried next scheduler cycle.
                logger.exception(
                    "Neironych video retry queue update delayed gen=%s", gen_id
                )


async def _count_missing_id_alerts() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=settings.NEIRONYCH_VIDEO_ALERT_AGE_SECONDS
    )
    async with AsyncSessionLocal() as session:
        value = await session.scalar(
            select(func.count()).select_from(Generation).where(
                Generation.gen_type == GenerationType.video,
                Generation.model.in_(tuple(PRODUCT_MODELS)),
                Generation.status.in_((GenerationStatus.pending, GenerationStatus.processing)),
                or_(Generation.task_id.is_(None), Generation.task_id == ""),
                Generation.created_at <= cutoff,
            )
        )
        await session.rollback()
        return int(value or 0)


async def _process_bounded_batch(ids: list[int], action, stop: asyncio.Event | None) -> list[bool]:
    semaphore = asyncio.Semaphore(settings.NEIRONYCH_VIDEO_RECONCILE_CONCURRENCY)

    async def process(gen_id: int) -> bool:
        if stop is not None and stop.is_set():
            return False
        try:
            async with semaphore:
                if stop is not None and stop.is_set():
                    return False
                return await action(gen_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Neironych video recovery item failed gen=%s", gen_id)
            return False

    return list(await asyncio.gather(*(process(gen_id) for gen_id in ids)))


async def _run_expired_lane(stop: asyncio.Event | None) -> list[bool]:
    return await _process_bounded_batch(
        await _load_expired_seedance_batch(), _expire_stuck_seedance_video, stop
    )


async def _active_ids_not_expired(ids: list[int]) -> list[int]:
    if not ids:
        return []
    async with AsyncSessionLocal() as session:
        live = (await session.execute(select(Generation).where(Generation.id.in_(ids)))).scalars().all()
        await session.rollback()
    overdue = {
        gen.id for gen in live
        if gen.gen_type == GenerationType.video and gen.model in PRODUCT_MODELS
        and str(gen.task_id or "").startswith(_NEIRONYCH_TASK_PREFIXES)
        and (datetime.now(timezone.utc) - _seedance_started_at(gen)).total_seconds()
        >= settings.SEEDANCE_AUTO_REFUND_SECONDS
    }
    return [ident for ident in ids if ident not in overdue]


async def _run_active_video_lane(stop: asyncio.Event | None) -> list[bool]:
    ids = await _load_batch(_eligible_video_query(), _video_cursor)
    # Expired tasks have a dedicated lane; don't steal their provider lease.
    ids = await _active_ids_not_expired(ids)
    return await _process_bounded_batch(ids, _process_active_video, stop)


async def _run_notices_lane(stop: asyncio.Event | None) -> list[bool]:
    try:
        ids = await _load_notice_batch()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Outbox is committed in Postgres; temporary Redis notice downtime
        # must not prevent expired tasks from being safely settled.
        logger.warning("Neironych notice queue unavailable error=%s", type(exc).__name__)
        return []
    return await _process_bounded_batch(ids, _process_delivery_notice, stop)


async def _run_refund_supplier_review_lane(stop: asyncio.Event | None) -> list[bool]:
    ids = await _load_batch(_provider_refund_review_query(), _refund_review_cursor)
    return await _process_bounded_batch(ids, _review_refunded_provider_task, stop)


async def reconcile_neironych_videos_once(stop: asyncio.Event | None = None) -> dict[str, int]:
    """Independent bounded lanes; slow GETs never starve Telegram delivery."""
    expired, video_results, notice_results, supplier_reviews = await asyncio.gather(
        _run_expired_lane(stop),
        _run_active_video_lane(stop),
        _run_notices_lane(stop),
        _run_refund_supplier_review_lane(stop),
    )
    checked = len(video_results)
    notices = len(notice_results)
    notice_sent = sum(bool(result) for result in notice_results)
    missing = await _count_missing_id_alerts() if not stop or not stop.is_set() else 0
    global _last_missing_id_warning
    if missing:
        now = datetime.now(timezone.utc)
        if (
            _last_missing_id_warning is None
            or now - _last_missing_id_warning >= timedelta(minutes=15)
        ):
            _last_missing_id_warning = now
            logger.warning("Seedance submitted video missing provider task ID count=%s", missing)
    else:
        _last_missing_id_warning = None
    return {
        "checked": checked,
        "expired": sum(bool(result) for result in expired),
        "notices": notices,
        "sent": notice_sent,
        "missing_ids": missing,
        "supplier_reviews": sum(bool(result) for result in supplier_reviews),
    }


async def run_neironych_video_reconcile_scheduler(stop: asyncio.Event) -> None:
    logger.info("Neironych Seedance video recovery scheduler started")
    while not stop.is_set():
        try:
            stats = await reconcile_neironych_videos_once(stop)
            if any(stats.values()):
                logger.info("Neironych Seedance video recovery summary=%s", stats)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Neironych Seedance video scheduler cycle failed")
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=settings.NEIRONYCH_VIDEO_RECONCILE_INTERVAL_SECONDS
            )
        except asyncio.TimeoutError:
            pass
