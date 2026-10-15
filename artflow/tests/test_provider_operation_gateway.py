from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import provider_billing
from api import provider_operation_bindings as _bindings  # noqa: F401
from api.provider_contract_catalog import ALL_CONTRACTS
from api.provider_operation_registry import (
    OPERATION_SPECS,
    PUBLIC_API_CONTRACT_IDS,
    OperationSpec,
    PollKind,
    execute_operation,
    get_operation_spec,
    validate_operation_params,
)
from api.provider_smoke_manifest import SMOKE_CASES
from db.models import GenerationType


def test_every_catalog_contract_has_public_executor_and_smoke_case() -> None:
    catalog_ids = {contract.contract_id for contract in ALL_CONTRACTS}
    assert set(OPERATION_SPECS) == catalog_ids
    assert set(PUBLIC_API_CONTRACT_IDS) == catalog_ids
    assert set(SMOKE_CASES) == catalog_ids


def test_primary_video_contracts_use_full_typed_implementations() -> None:
    assert get_operation_spec("video.kling30").executor.__name__ == "create_kling_30_video"
    assert get_operation_spec("video.seedance2").executor.__name__ == "create_seedance_task"
    assert get_operation_spec("video.wan27.i2v").executor.__name__ == "create_wan_image_to_video"
    assert get_operation_spec("video.happyhorse.i2v").executor.__name__ == "create_happyhorse_image_to_video"


def test_llm_contracts_have_exact_provider_bindings() -> None:
    responses = get_operation_spec("llm.kie.responses")
    claude = get_operation_spec("llm.kie.claude")
    comet = get_operation_spec("llm.comet.chat")

    assert responses.fixed["provider"] == "kie_responses"
    assert claude.fixed["provider"] == "kie_claude"
    assert comet.fixed["provider"] == "comet_chat"
    assert responses.poll_kind == PollKind.NONE


def test_unknown_operation_parameter_is_rejected_before_provider() -> None:
    spec = get_operation_spec("video.kling26.t2v")
    with pytest.raises(ValueError, match="Unsupported parameters"):
        validate_operation_params(
            spec,
            {
                "prompt": "Smoke",
                "duration": 5,
                "invented_provider_field": True,
            },
        )


@pytest.mark.asyncio
async def test_direct_operation_finishes_without_fake_task() -> None:
    async def direct_executor(prompt: str):
        return {"answer": prompt, "url": "https://example.test/result.png"}

    spec = OperationSpec(
        contract_id="test.direct",
        generation_type=GenerationType.image,
        model="test",
        executor=direct_executor,
        poll_kind=PollKind.NONE,
        billable=False,
    )
    started = await execute_operation(spec, {"prompt": "done"})

    assert started.task_id is None
    assert started.poll_kind == PollKind.NONE
    assert started.result_urls == ("https://example.test/result.png",)
    assert started.output == {"answer": "done", "url": "https://example.test/result.png"}


@pytest.mark.asyncio
async def test_refund_generation_once_marks_row_before_credit(monkeypatch) -> None:
    generation = SimpleNamespace(
        id=7,
        tg_id=42,
        input_params={"contract_id": "video.test"},
    )
    scalar_result = SimpleNamespace(scalar_one_or_none=lambda: generation)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=scalar_result),
        flush=AsyncMock(),
    )
    add_credits = AsyncMock()
    monkeypatch.setattr(provider_billing.repo, "add_credits", add_credits)

    refunded = await provider_billing.refund_generation_once(
        session,
        user_id=42,
        credits=9,
        generation_id=7,
        contract_id="video.test",
    )

    assert refunded is True
    assert generation.input_params["refund_applied"] is True
    session.flush.assert_awaited_once()
    add_credits.assert_awaited_once_with(
        session,
        42,
        9,
        reason="provider_operation_refund:video.test",
        ref_id=7,
    )


@pytest.mark.asyncio
async def test_refund_generation_once_is_idempotent(monkeypatch) -> None:
    generation = SimpleNamespace(
        id=7,
        tg_id=42,
        input_params={"refund_applied": True},
    )
    scalar_result = SimpleNamespace(scalar_one_or_none=lambda: generation)
    session = SimpleNamespace(execute=AsyncMock(return_value=scalar_result), flush=AsyncMock())
    add_credits = AsyncMock()
    monkeypatch.setattr(provider_billing.repo, "add_credits", add_credits)

    refunded = await provider_billing.refund_generation_once(
        session,
        user_id=42,
        credits=9,
        generation_id=7,
        contract_id="video.test",
    )

    assert refunded is False
    add_credits.assert_not_awaited()
