"""Authenticated public API for every registered provider contract."""
from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.provider_contract_catalog import CONTRACTS_BY_ID
from api.provider_operation_registry import (
    PUBLIC_API_CONTRACT_IDS,
    OperationSpec,
    execute_operation,
    get_operation_spec,
    poll_operation,
    resolve_operation_price,
)
from api.web.deps import WebUser, get_current_user
from db import repository as repo
from db.models import GenerationStatus
from db.session import get_session

router = APIRouter(prefix="/provider-operations", tags=["provider-operations"])


class ProviderOperationRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class ProviderOperationAccepted(BaseModel):
    generation_id: int | None = None
    contract_id: str
    model: str
    status: str
    credits: int = 0
    task_id: str | None = None
    result_urls: list[str] = Field(default_factory=list)
    output: Any = None


class ProviderOperationStatus(BaseModel):
    generation_id: int
    contract_id: str
    model: str
    status: str
    credits: int
    task_id: str | None = None
    result_urls: list[str] = Field(default_factory=list)
    error: str | None = None
    output: Any = None


class ContractSummary(BaseModel):
    contract_id: str
    provider: str
    model: str
    modes: list[str]
    billable: bool
    docs_verified_on: str
    official_docs: list[str]


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return str(value)


def _stored_params(
    contract_id: str,
    params: dict[str, Any],
    *,
    provider: str = "",
    poll_kind: str = "",
) -> dict[str, Any]:
    # Input params are needed for truthful re-polling and diagnostics, but raw
    # base64 media must never be copied into generation history.
    redacted: dict[str, Any] = {}
    for key, value in params.items():
        if "base64" in key.lower():
            redacted[key] = "<redacted>"
        else:
            redacted[key] = _jsonable(value)
    return {
        "contract_id": contract_id,
        "provider": provider,
        "poll_kind": poll_kind,
        "params": redacted,
    }


async def _refund(
    session: AsyncSession,
    *,
    user_id: int,
    credits: int,
    generation_id: int | None,
    contract_id: str,
) -> None:
    if credits <= 0:
        return
    await repo.add_credits(
        session,
        user_id,
        credits,
        reason=f"provider_operation_refund:{contract_id}",
        ref_id=generation_id,
    )


async def _load_owned_generation(
    session: AsyncSession,
    generation_id: int,
    user_id: int,
):
    generation = await repo.get_generation(session, generation_id)
    if generation is None or generation.tg_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
    input_params = generation.input_params if isinstance(generation.input_params, dict) else {}
    contract_id = str(input_params.get("contract_id") or "")
    if contract_id not in PUBLIC_API_CONTRACT_IDS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Generation is not a provider-operation task")
    return generation, contract_id


@router.get("/contracts", response_model=list[ContractSummary])
async def list_provider_contracts(
    _: WebUser = Depends(get_current_user),
) -> list[ContractSummary]:
    result: list[ContractSummary] = []
    for contract_id in sorted(PUBLIC_API_CONTRACT_IDS):
        contract = CONTRACTS_BY_ID[contract_id]
        spec = get_operation_spec(contract_id)
        result.append(
            ContractSummary(
                contract_id=contract.contract_id,
                provider=contract.provider,
                model=contract.model,
                modes=list(contract.modes),
                billable=spec.billable,
                docs_verified_on=contract.docs_verified_on,
                official_docs=list(contract.official_docs),
            )
        )
    return result


@router.post(
    "/{contract_id}",
    response_model=ProviderOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_provider_operation(
    contract_id: str,
    request: ProviderOperationRequest,
    user: WebUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProviderOperationAccepted:
    try:
        spec: OperationSpec = get_operation_spec(contract_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    try:
        credits = await resolve_operation_price(session, spec, request.params)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Operation is disabled until an active tariff is configured: {exc}",
        ) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    if credits > 0:
        spent = await repo.spend_credits(
            session,
            user.tg_id,
            credits,
            reason=f"provider_operation:{contract_id}",
        )
        if not spent:
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Insufficient credits")

    prompt = str(request.params.get("prompt") or request.params.get("content") or "")[:4000]
    generation = await repo.create_generation(
        session,
        user.tg_id,
        spec.generation_type,
        spec.model,
        prompt,
        credits,
        input_params=_stored_params(contract_id, request.params),
    )

    try:
        started = await execute_operation(spec, dict(request.params))
    except (TypeError, ValueError) as exc:
        await _refund(
            session,
            user_id=user.tg_id,
            credits=credits,
            generation_id=generation.id,
            contract_id=contract_id,
        )
        await repo.update_generation_status(
            session,
            generation.id,
            GenerationStatus.FAILED,
            error_message=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        await _refund(
            session,
            user_id=user.tg_id,
            credits=credits,
            generation_id=generation.id,
            contract_id=contract_id,
        )
        await repo.update_generation_status(
            session,
            generation.id,
            GenerationStatus.FAILED,
            error_message=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Provider operation failed to start") from exc

    generation.input_params = _stored_params(
        contract_id,
        request.params,
        provider=started.provider,
        poll_kind=started.poll_kind.value,
    )
    generation.provider = started.provider

    if started.task_id:
        await repo.update_generation_task(session, generation.id, started.task_id)
        await repo.update_generation_status(session, generation.id, GenerationStatus.PROCESSING)
        return ProviderOperationAccepted(
            generation_id=generation.id,
            contract_id=contract_id,
            model=spec.model,
            status=GenerationStatus.PROCESSING.value,
            credits=credits,
            task_id=started.task_id,
            result_urls=list(started.result_urls),
            output=_jsonable(started.output),
        )

    await repo.update_generation_status(
        session,
        generation.id,
        GenerationStatus.COMPLETED,
        result_urls=list(started.result_urls),
    )
    return ProviderOperationAccepted(
        generation_id=generation.id,
        contract_id=contract_id,
        model=spec.model,
        status=GenerationStatus.COMPLETED.value,
        credits=credits,
        result_urls=list(started.result_urls),
        output=_jsonable(started.output),
    )


@router.get("/generations/{generation_id}", response_model=ProviderOperationStatus)
async def get_provider_operation_status(
    generation_id: int,
    user: WebUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProviderOperationStatus:
    generation, contract_id = await _load_owned_generation(session, generation_id, user.tg_id)
    spec = get_operation_spec(contract_id)

    if generation.status in {
        GenerationStatus.COMPLETED,
        GenerationStatus.FAILED,
        GenerationStatus.CANCELLED,
    }:
        return ProviderOperationStatus(
            generation_id=generation.id,
            contract_id=contract_id,
            model=generation.model,
            status=generation.status.value,
            credits=generation.credits_spent,
            task_id=generation.task_id,
            result_urls=list(generation.result_urls or []),
            error=generation.error_message,
        )

    if not generation.task_id:
        return ProviderOperationStatus(
            generation_id=generation.id,
            contract_id=contract_id,
            model=generation.model,
            status=generation.status.value,
            credits=generation.credits_spent,
        )

    try:
        provider_status = await poll_operation(spec, generation.task_id)
    except Exception as exc:
        return ProviderOperationStatus(
            generation_id=generation.id,
            contract_id=contract_id,
            model=generation.model,
            status=GenerationStatus.PROCESSING.value,
            credits=generation.credits_spent,
            task_id=generation.task_id,
            error=f"Status check temporarily failed: {exc}",
        )

    if provider_status.state == "completed":
        await repo.update_generation_status(
            session,
            generation.id,
            GenerationStatus.COMPLETED,
            result_urls=list(provider_status.result_urls),
        )
        generation.status = GenerationStatus.COMPLETED
        generation.result_urls = list(provider_status.result_urls)
    elif provider_status.state == "failed":
        await _refund(
            session,
            user_id=user.tg_id,
            credits=generation.credits_spent,
            generation_id=generation.id,
            contract_id=contract_id,
        )
        await repo.update_generation_status(
            session,
            generation.id,
            GenerationStatus.FAILED,
            error_message=provider_status.error or "Provider task failed",
        )
        generation.status = GenerationStatus.FAILED
        generation.error_message = provider_status.error or "Provider task failed"

    return ProviderOperationStatus(
        generation_id=generation.id,
        contract_id=contract_id,
        model=generation.model,
        status=generation.status.value,
        credits=generation.credits_spent,
        task_id=generation.task_id,
        result_urls=list(generation.result_urls or []),
        error=generation.error_message,
        output=_jsonable(provider_status.output),
    )
