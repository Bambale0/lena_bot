"""Atomic wallet/ledger/job/intent admission for Kling 4; one commit before I/O."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from db import repository as repo
from db.models import Generation, GenerationStatus, GenerationType, Kling4Intent, User


def canonical_intent(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="Kling 4 requires a valid intent_id") from exc


async def reserve_kling4(
    session,
    *,
    user_id: int,
    intent_id: str,
    model: str,
    prompt: str,
    params: dict,
    credits: float,
    surface: str,
):
    intent_id = canonical_intent(intent_id)
    fingerprint = hashlib.sha256(
        json.dumps(
            {"model": model, "prompt": prompt, "params": params}, sort_keys=True, ensure_ascii=True
        ).encode()
    ).hexdigest()
    # Serialize admission by user, including a concurrent double click.
    owner = (
        await session.execute(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    existing = await session.get(Kling4Intent, intent_id)
    if existing:
        if existing.user_id != user_id or existing.payload_hash != fingerprint:
            raise HTTPException(status_code=409, detail="Intent already belongs to another request")
        gen = await session.get(Generation, existing.generation_id)
        await session.commit()
        return gen, False
    if float(owner.credits) < credits:
        raise HTTPException(status_code=402, detail="Недостаточно кредитов")
    if await repo.count_user_active_generations(session, user_id) >= 3:
        raise HTTPException(status_code=429, detail="Слишком много активных генераций")
    gen = Generation(
        user_id=user_id,
        model=model,
        gen_type=GenerationType.video,
        prompt=prompt,
        credits_spent=credits,
        status=GenerationStatus.pending,
        input_params=json.dumps(params, ensure_ascii=False),
    )
    session.add(gen)
    await session.flush()
    now = datetime.now(timezone.utc).isoformat()
    stored = {
        **params,
        repo.KIE_VIDEO_CALLBACK_KEY: {
            "generation_id": gen.id,
            "surface": surface,
            "registered_at": now,
        },
    }
    # Staging is free and occurs after atomic reservation. Crash recovery never
    # replays a POST: only a committed submitting marker may cross the boundary.
    gen.input_params = json.dumps(stored, ensure_ascii=False)
    owner.credits = float(owner.credits) - credits
    await repo._insert_credit_ledger(
        session,
        user_id=user_id,
        delta=-credits,
        balance_after=owner.credits,
        entry_type="spend",
        source_type="generation",
        source_id=str(gen.id),
        note="kling4_reserve",
    )
    session.add(
        Kling4Intent(
            intent_id=intent_id, user_id=user_id, generation_id=gen.id, payload_hash=fingerprint
        )
    )
    await session.commit()
    await session.refresh(gen)
    return gen, True
