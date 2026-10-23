"""Safe single-POST primary Neironych / standby KIE routing."""
from unittest.mock import AsyncMock

import pytest

from api.neironych_seedance import NeironychSeedanceError, NeironychSubmissionUnknown
from api.wan30_contract import Wan30Request
from api.wan30_routing import Wan30Submitted, submit_wan30


def req():
    return Wan30Request(model="wan/3-0-video", prompt="A small paper boat", duration=5)


@pytest.mark.asyncio
async def test_wan30_active_neironych_primary_gets_only_one_submit():
    models = AsyncMock(return_value=["wan-real-approved-model"])
    n = AsyncMock(return_value="run_123")
    k = AsyncMock()
    out = await submit_wan30(
        req(), neironych_model_id="wan-real-approved-model",
        fetch_neironych_models=models, send_neironych=n, send_kie=k,
    )
    assert out == Wan30Submitted(task_id="neironych:run_123", provider="neironych")
    assert n.await_count == 1
    assert n.await_args.args[0]["model"] == "wan-real-approved-model"
    k.assert_not_awaited()


@pytest.mark.asyncio
async def test_wan30_absent_from_neironych_catalog_uses_kie_without_neironych_post():
    n = AsyncMock()
    k = AsyncMock(return_value="kie_345")
    out = await submit_wan30(
        req(), neironych_model_id="wan-not-enabled",
        fetch_neironych_models=AsyncMock(return_value=["seedance-2.5"]),
        send_neironych=n, send_kie=k,
    )
    assert out == Wan30Submitted(task_id="kie_345", provider="kieai")
    n.assert_not_awaited()
    assert k.await_args.args[0]["model"] == "wan/3-0-video"


@pytest.mark.asyncio
async def test_missing_neironych_mapping_is_kie_standby_without_paid_probe():
    n = AsyncMock()
    lookup = AsyncMock()
    k = AsyncMock(return_value="kie_999")
    out = await submit_wan30(
        req(), neironych_model_id="",
        fetch_neironych_models=lookup,
        send_neironych=n, send_kie=k,
    )
    assert out.provider == "kieai"
    lookup.assert_not_awaited()
    n.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirmed_primary_balance_rejection_uses_kie_same_model():
    n = AsyncMock(side_effect=NeironychSeedanceError(
        "balance", status_code=402,payload={"detail":"insufficient_balance"},
    ))
    k = AsyncMock(return_value="kie_fallback")
    out = await submit_wan30(
        req(), neironych_model_id="wan-real-approved-model",
        fetch_neironych_models=AsyncMock(return_value=["wan-real-approved-model"]),
        send_neironych=n, send_kie=k,
    )
    assert out == Wan30Submitted(task_id="kie_fallback", provider="kieai")
    assert n.await_count == 1
    assert k.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("err", [
    NeironychSubmissionUnknown("d4496f2e-37d8-4b87-bba2-330374892b49","apix-wan30-55"),
    NeironychSeedanceError("gateway 5xx",status_code=503,payload={"detail":"temporary"}),
    NeironychSeedanceError("fake rejection",status_code=402,payload={"detail":"unknown"}),
])
async def test_unknown_or_unverified_neironych_failure_never_creates_second_paid_task(err):
    n = AsyncMock(side_effect=err)
    k = AsyncMock()
    with pytest.raises(type(err)):
        await submit_wan30(
            req(), neironych_model_id="wan-real-approved-model",
            fetch_neironych_models=AsyncMock(return_value=["wan-real-approved-model"]),
            send_neironych=n, send_kie=k,
        )
    k.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_neironych_catalog_error_prevents_paid_submission():
    n=AsyncMock()
    k=AsyncMock()
    with pytest.raises(RuntimeError,match="catalog"):
        await submit_wan30(
            req(),neironych_model_id="wan-real-approved-model",
            fetch_neironych_models=AsyncMock(side_effect=TimeoutError("unreachable")),
            send_neironych=n,send_kie=k,
        )
    n.assert_not_awaited()
    k.assert_not_awaited()



@pytest.mark.asyncio
async def test_primary_missing_provider_task_id_is_not_accepted_as_success():
    k=AsyncMock()
    with pytest.raises(RuntimeError, match="task ID"):
        await submit_wan30(
            req(), neironych_model_id="wan-real-approved-model",
            fetch_neironych_models=AsyncMock(return_value=["wan-real-approved-model"]),
            send_neironych=AsyncMock(return_value=""),
            send_kie=k,
        )
    k.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_disabled_standby_never_posts_to_kie_on_rejection():
    rejection = NeironychSeedanceError("balance", status_code=402, payload={"detail": "insufficient_balance"})
    kie = AsyncMock()
    with pytest.raises(NeironychSeedanceError):
        await submit_wan30(req(), neironych_model_id="wan-3", fetch_neironych_models=AsyncMock(return_value=["wan-3"]),
                           send_neironych=AsyncMock(side_effect=rejection), send_kie=kie, allow_kie=False)
    kie.assert_not_awaited()
