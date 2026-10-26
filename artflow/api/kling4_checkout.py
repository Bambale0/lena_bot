"""Shared Kling 4 launch used by the existing site/Mini App and bot."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from pydantic import ValidationError

from api import kieai_client
from api.kling4_contract import KEYFRAME_MODEL, Kling4Input
from api.kling4_launch import get_kling4_quote, stage_kling4_payload
from core.config import settings
from core.kie_seedance_callback import callback_url_for_generation
from core.kling4_access import require_kling4_access
from db import repository as repo
from db.kling4_repository import canonical_intent, reserve_kling4
from db.models import Generation, Kling4Intent

logger = logging.getLogger(__name__)


def request_input(body) -> Kling4Input:
    values = body.kling4.model_dump() if body.kling4 else {}
    values.update(
        duration=body.duration, resolution=body.resolution or "720p", aspect_ratio=body.aspect_ratio
    )
    refs = list(dict.fromkeys([url for url in [body.image_url, *body.reference_urls] if url]))
    if body.model == KEYFRAME_MODEL:
        if refs and not (
            values.get("first_frame_url")
            or values.get("keyframe_urls")
            or values.get("last_frame_url")
        ):
            values["first_frame_url"] = refs[0]
            if len(refs) > 1:
                values["last_frame_url"] = refs[-1]
                values["keyframe_urls"] = refs[1:-1]
        if body.video_url:
            raise ValueError("Keyframe не принимает видео")
    else:
        if refs:
            values["image_urls"] = list(dict.fromkeys(refs + values.get("image_urls", [])))
        if body.video_url:
            values["video_urls"] = list(
                dict.fromkeys([body.video_url] + values.get("video_urls", []))
            )
    if (
        body.audio_ids
        or body.character_ids
        or body.seed is not None
        or body.video_start
        or body.video_end is not None
    ):
        raise ValueError("Kling 4 не поддерживает Omni ID, seed или обрезку по таймкодам")
    return Kling4Input(**values)


async def quote_kling4(body, prompt, session, user):
    await require_kling4_access(session, user)
    try:
        data = request_input(body)
        quote = await get_kling4_quote(session, body.model, prompt, data, user_id=user.id)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (OSError, RuntimeError, TimeoutError) as exc:
        logger.warning("Kling4 preflight failed type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail="Не удалось проверить материалы Kling 4; кредиты не списаны"
        ) from exc
    return data, quote


def quote_response(body, data, quote, user):
    balance = float(user.credits or 0)
    return dict(
        model=body.model,
        cost_credits=quote.credits,
        balance_credits=balance,
        can_run=balance >= quote.credits,
        output_seconds=data.duration,
        reference_seconds=quote.reference_seconds,
        billable_seconds=quote.billable_seconds,
        reference_count=quote.reference_count,
        rate_credits_per_second=quote.rate,
        tariff_key=quote.tariff_key,
    )


async def create_kling4_generation(
    body,
    prompt,
    session,
    user,
    *,
    surface,
    callback_url,
    admission_guard: Callable[[], Awaitable[None]] | None = None,
):
    await require_kling4_access(session, user)
    intent_id = canonical_intent(body.intent_id)
    # A completed/uncertain intent is safe to read after a restart or tariff change.
    existing = await session.get(Kling4Intent, intent_id)
    if existing:
        if existing.user_id != user.id:
            raise HTTPException(status_code=409, detail="Intent already used")
        gen = await session.get(Generation, existing.generation_id)
        from db.repeat_lookup import parse_input_params

        try:
            same_input = (
                parse_input_params(gen.input_params).get("kling4")
                == request_input(body).model_dump()
            )
        except ValueError:
            same_input = False
        if gen.model != body.model or gen.prompt != prompt or not same_input:
            raise HTTPException(status_code=409, detail="Intent belongs to another request")
        return gen
    data, quote = await quote_kling4(body, prompt, session, user)
    if body.quoted_credits is None or round(body.quoted_credits, 6) != round(quote.credits, 6):
        raise HTTPException(
            status_code=409, detail="Цена Kling 4 изменилась. Проверь сумму и подтверди запуск"
        )
    if not settings.KIE_WEBHOOK_HMAC_KEY:
        raise HTTPException(status_code=503, detail="Kling 4: не настроена защита callback")
    from api.miniapp_routes import MAX_CONCURRENT

    if float(user.credits or 0) < quote.credits:
        raise HTTPException(status_code=402, detail="Недостаточно кредитов")
    if await repo.count_user_active_generations(session, user.id) >= MAX_CONCURRENT:
        raise HTTPException(status_code=429, detail="Слишком много активных генераций")
    try:
        staged = await stage_kling4_payload(body.model, prompt, data)
    except (ValueError, OSError, RuntimeError, TimeoutError) as exc:
        logger.warning("Kling4 staging failed type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail="Не удалось подготовить материалы; кредиты не списаны"
        ) from exc
    params = dict(
        kling4=data.model_dump(),
        intent_id=intent_id,
        mode=body.mode,
        duration=data.duration,
        resolution=data.resolution,
        aspect_ratio=data.aspect_ratio,
        image_url=data.image_urls,
        reference_video_url=data.video_urls,
        billing_output_seconds=data.duration,
        billing_reference_seconds=quote.reference_seconds,
        billing_total_seconds=quote.billable_seconds,
        billing_rate=quote.rate,
        billing_tariff_key=quote.tariff_key,
    )
    await require_kling4_access(session, user)
    if admission_guard is not None:
        await admission_guard()
    gen, fresh = await reserve_kling4(
        session,
        user_id=user.id,
        intent_id=intent_id,
        model=body.model,
        prompt=prompt,
        params=params,
        credits=quote.credits,
        surface=surface,
        max_active_generations=MAX_CONCURRENT,
    )
    if not fresh:
        return gen
    gen_id = gen.id
    if not await repo.begin_kie_video_submission(session, gen_id, intent_id):
        await session.refresh(gen)
        return gen
    # There is exactly one POST; unknown transport/response outcomes retain money.
    try:
        response = await kieai_client.create_task(
            staged, callback_url=callback_url_for_generation(callback_url, gen_id)
        )
    except kieai_client.KieDefiniteRejection as exc:
        await session.rollback()
        await repo.fail_generation_and_refund(
            session, gen_id, str(exc), refund_note="kling4_definite_rejection"
        )
    except Exception as exc:
        logger.warning("Kling4 submission unknown gen=%s type=%s", gen_id, type(exc).__name__)
        await session.rollback()
        await repo.mark_kie_video_submission_unknown(session, gen_id)
    else:
        task_id = response["data"]["taskId"]
        # bind uses a row lock and cannot overwrite a callback's final result.
        await repo.bind_kie_video_callback(session, gen_id, task_id)
        logger.info("Kling4 submitted gen=%s task=%s tariff=%s", gen_id, task_id, quote.tariff_key)
    await session.refresh(gen)
    return gen
