"""Paid Wan3 submission route: verified Neironych primary, KIE standby.

Never fallback after ambiguous acceptance (timeouts, 5xx, non-JSON, missing ID).
A model not advertised by Neironych /v1/models is not sent a paid test POST.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from api.neironych_seedance import (
    NeironychPreSubmitFailure,
    NeironychSeedanceError,
    NeironychSubmissionUnknown,
)
from api.wan30_contract import (
    Wan30Request,
    build_kie_wan30_payload,
    build_neironych_wan30_payload,
    wan30_supported_by_neironych,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Wan30Submitted:
    task_id: str
    provider: str


# The exact detail/status pair is emitted by Neironych's admission stage.
# A raw HTTP 4xx alone is not proof that no paid task was accepted.
_ADMISSION_REJECTIONS = {
    (401, "api_key_required"),
    (401, "invalid_api_key"),
    (402, "insufficient_balance"),
    (403, "partner_not_active"),
    (404, "model_not_available"),
    (409, "capability_mismatch"),
    (422, "invalid_request_contract"),
    (422, "invalid_idempotency_key"),
    (422, "invalid_client_request_id"),
}


def _confirmed_no_neironych_submission(exc: NeironychSeedanceError) -> bool:
    payload = exc.payload
    detail = payload.get("detail") if isinstance(payload, dict) else None
    return isinstance(detail, str) and (exc.status_code, detail) in _ADMISSION_REJECTIONS


async def submit_wan30(
    request: Wan30Request,
    *,
    neironych_model_id: str,
    fetch_neironych_models: Callable[[], Awaitable[list[str]]],
    send_neironych: Callable[[dict], Awaitable[str]],
    send_kie: Callable[[dict], Awaitable[str]],
    allow_kie: bool = True,
) -> Wan30Submitted:
    kie_payload = build_kie_wan30_payload(request)  # all validation before POST
    primary_model = str(neironych_model_id or "").strip()
    if primary_model and wan30_supported_by_neironych(request):
        try:
            current_models = await fetch_neironych_models()
        except Exception as exc:
            # Read-only availability could not be confirmed; don't gamble with
            # a paid submission or incorrectly switch to the backup provider.
            raise RuntimeError("Neironych model catalog is unavailable") from exc
        if primary_model in current_models:
            primary_payload = build_neironych_wan30_payload(
                request, provider_model=primary_model,
            )
            try:
                task_id = await send_neironych(primary_payload)
                if not isinstance(task_id, str) or not task_id.strip():
                    # An accepted POST with a lost ID is unresolved paid work.
                    raise RuntimeError("Neironych Wan accepted work without verified task ID")
                return Wan30Submitted(task_id=f"neironych:{task_id}", provider="neironych")
            except (NeironychSubmissionUnknown, NeironychPreSubmitFailure):
                raise
            except NeironychSeedanceError as exc:
                if not allow_kie or not _confirmed_no_neironych_submission(exc):
                    raise
                logger.warning(
                    "Wan3 Neironych rejected at admission; KIE backup model=%s code=%s",
                    request.model, exc.status_code,
                )
            # Other exceptions also cannot prove a paid task wasn't accepted.
    else:
        logger.info(
            "Wan3 KIE standby model=%s reason=%s",
            request.model,
            "model mapping unavailable" if not primary_model else "unsupported primary input",
        )
    if not allow_kie:
        raise ValueError("Wan request cannot use Neironych and KIE standby is disabled")
    task_id = await send_kie(kie_payload)
    return Wan30Submitted(task_id=task_id, provider="kieai")
