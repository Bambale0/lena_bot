"""Durable exact-model Nexus E-294 fallback to Neironych.

Only canonical confirmed failures qualify. A claimed generation is submitted
at most once; unknown Neironych outcomes are polled, never submitted again.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from api import neironych_image_adapter as native
from api import neironych_image_fallback_adapter as fallback_adapter
from api import nexus_image_adapter
from core.config import settings
from core.image_fallback_policy import EXACT_MODELS, fallback_enabled
from db import repository as repo
from db.models import GenerationStatus, GenerationType
from db.repeat_lookup import parse_input_params
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


def _request_id_for_generation(gen) -> str:
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"{settings.WEBHOOK_URL}:artflow:nexus-image-fallback:{gen.model}:{gen.id}",
    ))


def _original_params(gen) -> tuple[list[str], str, str]:
    params = parse_input_params(gen.input_params)
    if int(params.get("img_count") or 1) != 1:
        raise ValueError("Fallback requires exactly one image")
    refs = params.get("reference_images") or []
    if not isinstance(refs, list) or any(not isinstance(item, str) for item in refs):
        raise ValueError("Fallback requires original reference URLs")
    ratio = str(params.get("img_ratio") or "1:1")
    quality = str(params.get("img_quality") or "2K")
    fallback_adapter.build_fallback_image_payload(
        model_key=gen.model, prompt=gen.prompt, image_urls=refs,
        aspect_ratio=ratio, quality=quality,
    )
    return refs, ratio, quality


def _is_terminal_e294(gen, payload: dict) -> bool:
    if gen.gen_type != GenerationType.image or gen.model not in EXACT_MODELS:
        return False
    if gen.status not in {GenerationStatus.pending, GenerationStatus.processing}:
        return False
    task_id = str(gen.task_id or "").removeprefix("web:")
    if not nexus_image_adapter.is_nexus_task_id(task_id):
        return False
    if str(payload.get("task_id") or "") != nexus_image_adapter.strip_nexus_task_id(task_id):
        return False
    if str(payload.get("status") or "").lower() != "failed":
        return False
    return "e-294" in nexus_image_adapter._task_error(payload).casefold()


async def maybe_start_image_fallback(session, gen, payload: dict) -> bool:
    """Only call with canonical Nexus GET payload, never webhook body."""
    if not isinstance(payload, dict) or not _is_terminal_e294(gen, payload):
        return False
    if not await fallback_enabled(session, gen.model):
        return False
    try:
        _original_params(gen)
    except (TypeError, ValueError) as exc:
        logger.warning("Nexus fallback unsupported parameters gen=%s reason=%s", gen.id, type(exc).__name__)
        return False
    rid = _request_id_for_generation(gen)
    new_task_id = ("web:" if str(gen.task_id).startswith("web:") else "") + native.encode_task_id(rid)
    claimed = await repo.claim_nexus_image_fallback(
        session, gen.id, expected_task_id=gen.task_id,
        fallback_task_id=new_task_id, reason_code="E-294",
    )
    if not claimed:
        return False
    logger.warning("Image fallback claimed gen=%s model=%s from=nexus to=neironych reason=E-294", gen.id, gen.model)
    _spawn_image_fallback(gen.id, new_task_id)
    return True


def _spawn_image_fallback(gen_id: int, task_id: str) -> None:
    task = asyncio.create_task(_perform_image_fallback(gen_id, task_id))

    def on_done(finished):
        if not finished.cancelled() and finished.exception():
            logger.error("Fallback worker unhandled error gen=%s", gen_id, exc_info=finished.exception())

    task.add_done_callback(on_done)


async def _notify_failed_fallback(session, gen_id: int, refunded: float) -> None:
    gen = await repo.get_generation_by_id(session, gen_id)
    if not gen or str(gen.task_id or "").startswith("web:"):
        return
    try:
        from main import bot
        user = await repo.get_user_by_id(session, gen.user_id)
        if bot is not None and user:
            notice = "Изображение не создано: резервный генератор тоже недоступен."
            if refunded > 0:
                notice += f" {refunded:g} кредита возвращены."
            await bot.send_message(user.tg_id, notice + f" Задача #{gen_id}")
    except Exception as exc:
        logger.warning("Fallback failure notice deferred gen=%s type=%s", gen_id, type(exc).__name__)


async def _perform_image_fallback(gen_id: int, task_id: str) -> None:
    async with AsyncSessionLocal() as session:
        gen = await repo.get_generation_by_id(session, gen_id)
        if not gen or gen.task_id != task_id or gen.status not in {
            GenerationStatus.pending, GenerationStatus.processing,
        }:
            return
        try:
            refs, ratio, quality = _original_params(gen)
        except (ValueError, TypeError) as exc:
            logger.error("Fallback input unavailable gen=%s type=%s", gen_id, type(exc).__name__)
            changed, refunded = await repo.fail_generation_and_refund(
                session, gen_id, "Fallback input invalid",
                expected_task_id=task_id, refund_note="nexus_neironych:invalid_input",
            )
            if changed:
                await _notify_failed_fallback(session, gen_id, refunded)
            return
        prompt, model_key = gen.prompt, gen.model
        rid = native.decode_task_id(task_id)
        await session.rollback()  # Never hold an SQL transaction during a paid HTTP POST.

    if not rid:
        logger.error("Fallback persisted task identity invalid gen=%s", gen_id)
        return
    try:
        url = await fallback_adapter.generate_fallback_image(
            model_key=model_key, prompt=prompt, request_id=rid,
            image_urls=refs, aspect_ratio=ratio, quality=quality,
        )
    except native.NeironychImageRejected as exc:
        async with AsyncSessionLocal() as session:
            changed, refunded = await repo.fail_generation_and_refund(
                session, gen_id, "Neironych definitively rejected fallback",
                expected_task_id=task_id, refund_note="nexus_neironych:rejected",
            )
            if changed:
                await _notify_failed_fallback(session, gen_id, refunded)
        logger.warning("Fallback definitively rejected gen=%s status=%s", gen_id, exc.status_code)
        return
    except Exception as exc:
        # A timeout, HTTP 5xx or malformed result can mean the paid request was
        # accepted. Reconciliation may GET the same request; never POST again.
        logger.warning(
            "Fallback outcome deferred to reconciliation gen=%s type=%s",
            gen_id, type(exc).__name__,
        )
        return

    async with AsyncSessionLocal() as session:
        finished = await repo.finish_generation(
            session, gen_id, url, result_urls=[url], expected_task_id=task_id,
        )
        if finished is None:
            return
        if finished.image_session_id:
            await repo.update_image_session_last_result(
                session, finished.image_session_id, url, gen_id,
            )
        if not str(task_id).startswith("web:"):
            try:
                from api.miniapp_routes import _notify_direct_image_result_in_bot
                user = await repo.get_user_by_id(session, finished.user_id)
                if user:
                    await _notify_direct_image_result_in_bot(
                        user=user, gen=finished, result_urls=[url],
                    )
            except Exception as exc:
                logger.warning("Fallback delivery notice deferred gen=%s type=%s", gen_id, type(exc).__name__)
        logger.info("Image fallback settled gen=%s model=%s provider=neironych", gen_id, model_key)
