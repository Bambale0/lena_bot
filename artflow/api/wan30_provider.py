"""Wan 3.0 / Prime transport orchestrator with audited provider ordering.

No APIX user/billing entrypoint until the full quote/reserve/settle + UI
integration is independently audited. Neironych POST requires durable admission.
"""
from __future__ import annotations

import logging

import httpx

from api import kieai_client
from api.neironych_seedance import NeironychSeedanceClient
from api.neironych_seedance_runtime import SubmissionContext
from api.wan30_contract import (
    Wan30Request,
    build_neironych_wan30_payload,
    wan30_supported_by_neironych,
)
from api.wan30_neironych_transport import post_wan30_neironych
from api.wan30_routing import Wan30Submitted, submit_wan30
from core.config import settings
from core.wan30_routing_policy import get_wan30_route

logger = logging.getLogger(__name__)


async def resume_wan30_neironych_fallback(
    request: Wan30Request,
    *,
    idempotency_key: str,
    submission_context: SubmissionContext,
) -> Wan30Submitted:
    """Resume only a durably rejected KIE-primary attempt; never replay KIE."""
    route = await get_wan30_route(request.model)
    primary_id = str(route.neironych_model_id or "").strip()
    if route.policy != "kie_neironych":
        raise RuntimeError("Wan KIE-to-Neironych fallback is no longer enabled")
    if not settings.NEIRONYCH_API_KEY.strip() or not primary_id:
        raise RuntimeError("Neironych fallback is unavailable")
    if not wan30_supported_by_neironych(request):
        raise RuntimeError("Neironych fallback cannot preserve this Wan request")
    if (
        not submission_context.kie_started
        or not submission_context.kie_definitely_rejected
        or not callable(submission_context.before_submit)
    ):
        raise RuntimeError("Durable KIE rejection is required for fallback resume")

    async with httpx.AsyncClient(
        base_url=settings.NEIRONYCH_API_BASE_URL,
        timeout=httpx.Timeout(settings.NEIRONYCH_HTTP_TIMEOUT_SECONDS, connect=15.0),
        follow_redirects=False,
    ) as client:
        neironych = NeironychSeedanceClient(
            settings.NEIRONYCH_API_KEY,
            settings.NEIRONYCH_API_BASE_URL,
            client=client,
        )
        try:
            current_models = await neironych.list_models()
        except Exception as exc:
            raise RuntimeError("Neironych fallback catalog is unavailable") from exc
        if primary_id not in current_models:
            raise RuntimeError("Neironych fallback model is unavailable")
        payload = build_neironych_wan30_payload(
            request, provider_model=primary_id,
        )
        task_id = await post_wan30_neironych(
            client=client,
            api_key=settings.NEIRONYCH_API_KEY,
            payload=payload,
            idempotency_key=idempotency_key,
            client_request_id=submission_context.client_request_id,
            before_submit=submission_context.before_submit,
        )
    if not isinstance(task_id, str) or not task_id.strip():
        raise RuntimeError("Neironych Wan accepted work without verified task ID")
    return Wan30Submitted(task_id=f"neironych:{task_id}", provider="neironych")


async def submit_wan30_provider(
    request: Wan30Request,
    *,
    idempotency_key: str,
    callback_url: str | None = None,
    submission_context: SubmissionContext | None = None,
) -> Wan30Submitted:
    """Submit to one accepted provider task, preserving its provider task ID."""
    route = await get_wan30_route(request.model)
    primary_id = (
        route.neironych_model_id
        if route.policy != "kie_only" and settings.NEIRONYCH_API_KEY.strip()
        else ""
    )
    logger.info(
        "Wan route model=%s policy=%s revision=%s source=%s primary_configured=%s",
        request.model, route.policy, route.revision, route.source, bool(primary_id),
    )
    async with httpx.AsyncClient(
        base_url=settings.NEIRONYCH_API_BASE_URL,
        timeout=httpx.Timeout(settings.NEIRONYCH_HTTP_TIMEOUT_SECONDS, connect=15.0),
        follow_redirects=False,
    ) as client:
        neironych = NeironychSeedanceClient(
            settings.NEIRONYCH_API_KEY, settings.NEIRONYCH_API_BASE_URL, client=client,
        )

        async def send_neironych(payload: dict) -> str:
            if submission_context is None or not callable(submission_context.before_submit):
                raise RuntimeError("Neironych Wan primary requires durable submission journal")
            return await post_wan30_neironych(
                client=client,
                api_key=settings.NEIRONYCH_API_KEY,
                payload=payload,
                idempotency_key=idempotency_key,
                client_request_id=submission_context.client_request_id,
                before_submit=submission_context.before_submit,
            )

        async def send_kie(payload: dict) -> str:
            if submission_context is not None:
                if not callable(submission_context.before_kie_submit):
                    raise RuntimeError("Wan KIE paid POST requires a durable submission journal")
                # Whether KIE is primary or definite-rejection fallback, a
                # process crash after accepted POST must still be recoverable.
                await submission_context.before_kie_submit()
            try:
                response = await kieai_client.create_task(
                    payload, callback_url=callback_url,
                )
            except kieai_client.KieDefiniteRejection:
                if route.policy == "kie_neironych" and submission_context is not None:
                    persist_rejection = (
                        submission_context.after_kie_definite_rejection
                    )
                    if not callable(persist_rejection):
                        raise RuntimeError(
                            "Wan KIE rejection requires a durable fallback journal"
                        )
                    await persist_rejection()
                raise
            fields = response.get("data") if isinstance(response, dict) else None
            task_id = fields.get("taskId") if isinstance(fields, dict) else None
            # KIE's single-shot createTask classifies a missing ID as unknown;
            # this is defensive for any future mock/transport replacement.
            if not isinstance(task_id, str) or not task_id.strip():
                from api.kieai_client import KieSubmissionOutcomeUnknown
                raise KieSubmissionOutcomeUnknown("KIE Wan3 accepted task but task ID is unknown")
            return task_id

        return await submit_wan30(
            request,
            policy=route.policy,
            neironych_model_id=primary_id,
            fetch_neironych_models=neironych.list_models,
            send_neironych=send_neironych,
            send_kie=send_kie,
            allow_kie=route.policy != "neironych_only",
        )
