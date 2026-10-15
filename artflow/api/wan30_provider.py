"""Wan 3.0 / Prime transport orchestrator with KIE standby.

No APIX user/billing entrypoint until the full quote/reserve/settle + UI
integration is independently audited. Neironych POST requires durable admission.
"""
from __future__ import annotations

import httpx

from api import kieai_client
from api.neironych_seedance import NeironychSeedanceClient
from api.neironych_seedance_runtime import SubmissionContext
from api.wan30_contract import Wan30Request
from api.wan30_neironych_transport import post_wan30_neironych
from api.wan30_routing import Wan30Submitted, submit_wan30
from core.config import settings


def _primary_id(model: str) -> str:
    return str(
        settings.WAN30_PRIME_NEIRONYCH_MODEL_ID
        if model == "wan/3-0-video-prime" else settings.WAN30_NEIRONYCH_MODEL_ID
    ).strip()


async def submit_wan30_provider(
    request: Wan30Request,
    *,
    idempotency_key: str,
    callback_url: str | None = None,
    submission_context: SubmissionContext | None = None,
) -> Wan30Submitted:
    """Submit at most once to Neironych or KIE, preserving provider task ID."""
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
            response = await kieai_client.create_task(payload, callback_url=callback_url)
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
            neironych_model_id=_primary_id(request.model),
            fetch_neironych_models=neironych.list_models,
            send_neironych=send_neironych,
            send_kie=send_kie,
        )
