"""Bind signed KIE image callbacks after an uncertain one-shot submit."""
from fastapi import HTTPException
from sqlalchemy import select

from api import kieai_client, neironych_image_adapter
from core.provider_routing import SEEDREAM_5_MODELS
from db.models import Generation, GenerationStatus, GenerationType


async def bind_kie_callback(session, gen_id: int, provider_task_id: str):
    task = str(provider_task_id or "").strip()
    if not task or len(task) > 180:
        return None
    gen = (await session.execute(
        select(Generation).where(Generation.id == gen_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if gen is None or gen.gen_type != GenerationType.image or gen.model not in SEEDREAM_5_MODELS:
        await session.rollback()
        return None
    rid = neironych_image_adapter.client_request_id_for_generation(gen_id)
    marker = neironych_image_adapter.encode_kie_handoff_id(rid)
    prefix = "web:" if str(gen.task_id or "").startswith("web:") else ""
    if gen.status not in (GenerationStatus.pending, GenerationStatus.processing) or gen.task_id != prefix + marker:
        await session.commit()
        return None
    # Provider reads must not hold a generation row lock.
    await session.commit()
    await canonical_kie_status(task)
    gen = (await session.execute(
        select(Generation).where(Generation.id == gen_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if gen is None or gen.task_id != prefix + marker or gen.status not in (GenerationStatus.pending, GenerationStatus.processing):
        await session.commit()
        return None
    gen.task_id = prefix + task
    gen.status = GenerationStatus.processing
    await session.commit()
    return gen



async def canonical_kie_status(task_id: str) -> dict:
    """The signed URL correlates a generation; provider GET verifies the body."""
    try:
        payload = await kieai_client.get_task_status(task_id)
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or payload.get("code") != 200 or data.get("taskId") != task_id:
            raise ValueError("Invalid canonical KIE task")
        if data.get("model") not in SEEDREAM_5_MODELS:
            raise ValueError("Canonical Seedream model mismatch")
        state = data.get("state")
        if state not in {"waiting", "queuing", "generating", "success", "fail"}:
            raise ValueError("Unknown canonical KIE state")
        clean = {key: data[key] for key in ("taskId", "state", "resultJson", "failCode", "failMsg") if key in data}
        if state in {"waiting", "queuing", "generating"}:
            clean["state"] = "processing"
        return {"code": 200, "data": clean}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Seedream status unavailable; retry callback later") from exc
