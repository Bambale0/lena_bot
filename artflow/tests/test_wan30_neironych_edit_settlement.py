"""Regression: Wan3 native edit routing and exactly-once post-output billing."""
import json
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from api.wan30_contract import (
    Wan30Request,
    build_neironych_wan30_payload,
    wan30_max_billable_seconds,
    wan30_supported_by_neironych,
)
from api.wan30_launch import Wan30Quote
from db import repository as repo
from db.models import (
    Base,
    CreditLedgerEntry,
    Generation,
    GenerationStatus,
    GenerationType,
    PromptCategory,
    PromptStatus,
    User,
    UserPrompt,
)


def source_edit(*, duration=10, first_seconds=10.56, model="wan/3-0-video",
                aspect_ratio="adaptive"):
    return Wan30Request(
        model=model, mode="edit", prompt="Edit @Video 1 to look warmer",
        duration=duration, resolution="720p", aspect_ratio=aspect_ratio,
        reference_video_urls=("https://example.test/source.mp4",),
        reference_video_durations=(first_seconds,),
    )


def test_edit_native_contract_uses_documented_edit_selector_and_no_duration_or_ratio():
    request = source_edit(duration=10, first_seconds=10.56)
    assert wan30_supported_by_neironych(request)
    payload = build_neironych_wan30_payload(request, provider_model="wan-3")
    assert payload["omni_reference_task_type"] == "edit"
    assert payload["reference_videos"] == [{"url": "https://example.test/source.mp4"}]
    assert payload["resolution"] == "720p"
    for field in ("mode", "duration", "aspect_ratio", "size"):
        assert field not in payload


@pytest.mark.parametrize("edit_case", [
    source_edit(model="wan/3-0-video-prime"),
    source_edit(duration=15, first_seconds=10.56),
    source_edit(aspect_ratio="9:16"),
])
def test_native_edit_rejects_incompatible_semantics(edit_case):
    assert not wan30_supported_by_neironych(edit_case)


def test_edit_reserves_upper_bound_and_marks_billable_duration_unsettled():
    request = source_edit(duration=10, first_seconds=10.56)
    quote = Wan30Quote(request, billable_seconds=22, rate=4.0, credits=88.0, resolution="720p")
    params = quote.stored_params()
    assert params["wan30_billing"]["settled"] is False


def test_wan_edit_quote_covers_source_length_even_when_requested_duration_rounds_down():
    assert wan30_max_billable_seconds(source_edit(duration=10, first_seconds=10.99)) == 21.98


def test_duration_settlement_uses_verified_seconds_and_caps_at_reserved_amount():
    from api.wan30_settlement import calculate_wan30_settlement
    billing = {
        "mode": "edit", "rate": 4.0, "reserved_billable_seconds": 22,
        "input_video_seconds": 10.56, "reserved_credits": 88.0, "settled": False,
    }
    actual = calculate_wan30_settlement(billing, output_seconds=8.04, credits_spent=88.0)
    assert actual.billable_seconds == 19
    assert actual.final_credits == 76.0
    assert actual.refund_credits == 12.0
    assert actual.output_billable_seconds == 9
    fractional = calculate_wan30_settlement(
        billing, output_seconds=8.49, credits_spent=88.0,
    )
    assert fractional.billable_seconds == 20
    assert fractional.refund_credits == 8.0
    assert actual.overage_seconds == 0
    excess = calculate_wan30_settlement(billing, output_seconds=24.7, credits_spent=88.0)
    assert excess.final_credits == 88.0
    assert excess.refund_credits == 0.0
    assert excess.overage_seconds > 0
    with pytest.raises(ValueError):
        calculate_wan30_settlement(billing, output_seconds=float("nan"), credits_spent=88.0)


class SyncFacade:
    def __init__(self, session):
        self.sync = session

    async def execute(self, statement):
        return self.sync.execute(statement)

    async def commit(self):
        self.sync.commit()

    async def rollback(self):
        self.sync.rollback()

    async def flush(self):
        self.sync.flush()

    def add(self, entity):
        self.sync.add(entity)


@pytest.fixture
def settlement_db(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "wan3-settlement.db"))
    Base.metadata.create_all(engine, tables=[
        User.__table__, Generation.__table__, CreditLedgerEntry.__table__,
    ])
    quote = Wan30Quote(
        source_edit(duration=10, first_seconds=10.56),
        billable_seconds=22, rate=4.0, credits=88.0, resolution="720p",
    )
    with Session(engine) as session:
        session.add(User(id=700, tg_id=700, credits=100, referral_code="wan-native-edit"))
        session.add(Generation(
            id=701, user_id=700, model="wan/3-0-video", gen_type=GenerationType.video,
            status=GenerationStatus.processing, task_id="neironych:wan-edit-701",
            prompt="Make the sky brighter", credits_spent=88.0,
            input_params=json.dumps(quote.stored_params()),
        ))
        session.commit()
    yield engine
    engine.dispose()


@pytest.mark.asyncio
async def test_native_edit_completion_refunds_once_and_sets_final_ledger(settlement_db, monkeypatch):
    from api import wan30_settlement
    monkeypatch.setattr(repo, "mirror_url", AsyncMock(side_effect=lambda url: url))
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    monkeypatch.setattr(wan30_settlement, "probe_wan30_output_seconds", AsyncMock(return_value=8.04))
    url = "https://apixbotai.com/static/upload/provider-results/verified.mp4"
    with Session(settlement_db, expire_on_commit=False) as session:
        facade = SyncFacade(session)
        done = await repo.finish_generation(
            facade, 701, url, expected_task_id="neironych:wan-edit-701",
        )
        assert done and done.status == GenerationStatus.done
        assert done.credits_spent == 76.0
        assert json.loads(done.input_params)["wan30_billing"]["settled"] is True
        assert await repo.finish_generation(
            facade, 701, url, expected_task_id="neironych:wan-edit-701",
        ) is None
        assert (await repo.fail_generation_and_refund(facade, 701, "late callback")) == (False, 0.0)
        assert session.get(User, 700).credits == 112.0
        ledgers = session.scalars(select(CreditLedgerEntry)).all()
        assert len(ledgers) == 1
        assert ledgers[0].delta == 12.0
        assert ledgers[0].source_id == "701"


@pytest.mark.asyncio
async def test_native_edit_completion_ledger_failure_rolls_back_for_safe_retry(settlement_db, monkeypatch):
    from sqlalchemy import event

    from api import wan30_settlement
    monkeypatch.setattr(repo, "mirror_url", AsyncMock(side_effect=lambda url: url))
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    monkeypatch.setattr(wan30_settlement, "probe_wan30_output_seconds", AsyncMock(return_value=8.04))
    def fail_ledger(_conn, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("INSERT INTO CREDIT_LEDGER"):
            raise RuntimeError("ledger offline")
    event.listen(settlement_db, "before_cursor_execute", fail_ledger)
    try:
        with Session(settlement_db, expire_on_commit=False) as sync:
            with pytest.raises(RuntimeError, match="ledger offline"):
                await repo.finish_generation(
                    SyncFacade(sync), 701,
                    "https://apixbotai.com/static/upload/provider-results/verified.mp4",
                    expected_task_id="neironych:wan-edit-701",
                )
            sync.rollback()
    finally:
        event.remove(settlement_db, "before_cursor_execute", fail_ledger)
    with Session(settlement_db, expire_on_commit=False) as sync:
        assert sync.get(Generation, 701).status == GenerationStatus.processing
        assert sync.get(User, 700).credits == 100
        assert not sync.scalars(select(CreditLedgerEntry)).all()
        done = await repo.finish_generation(
            SyncFacade(sync), 701,
            "https://apixbotai.com/static/upload/provider-results/verified.mp4",
            expected_task_id="neironych:wan-edit-701",
        )
        assert done and done.credits_spent == 76.0


@pytest_asyncio.fixture
async def wan_pg_db(monkeypatch):
    """Disposable PostgreSQL schema: cross-session SELECT FOR UPDATE verification."""
    import os
    from uuid import uuid4

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    url = os.environ.get("APIX_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Requires disposable PostgreSQL")
    schema = "wan_edit_settlement_" + uuid4().hex
    control = create_async_engine(url)
    async with control.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}},
    )
    tables = [
        table for table in Base.metadata.sorted_tables
        if table.name in {"users", "image_sessions", "generations", "credit_ledger", "user_prompts"}
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    quote = Wan30Quote(
        source_edit(), billable_seconds=22, rate=4.0, credits=88.0,
        resolution="720p",
    )
    async with factory() as session:
        session.add(User(
            id=700, tg_id=700, credits=100, referral_code="wan-pg-test",
        ))
        await session.flush()
        session.add(Generation(
            id=701, user_id=700, model="wan/3-0-video",
            gen_type=GenerationType.video, status=GenerationStatus.processing,
            task_id="neironych:wan-edit-701", prompt="Make brighter",
            credits_spent=88.0, input_params=json.dumps(quote.stored_params()),
        ))
        await session.commit()
    monkeypatch.setattr(repo, "mirror_url", AsyncMock(side_effect=lambda url: url))
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    from api import wan30_settlement
    monkeypatch.setattr(
        wan30_settlement, "probe_wan30_output_seconds",
        AsyncMock(return_value=8.04),
    )
    try:
        yield factory
    finally:
        await engine.dispose()
        async with control.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()


@pytest.mark.asyncio
async def test_postgres_parallel_callback_and_poll_settle_once(wan_pg_db):
    import asyncio

    factory = wan_pg_db
    url = "https://apixbotai.com/static/upload/provider-results/verified.mp4"
    async def settle_one():
        async with factory() as session:
            return await repo.finish_generation(
                session, 701, url, expected_task_id="neironych:wan-edit-701",
            )
    results = await asyncio.wait_for(asyncio.gather(
        *[settle_one() for _ in range(5)],
    ), 20)
    assert sum(result is not None for result in results) == 1
    async with factory() as session:
        gen = await session.get(Generation, 701)
        user = await session.get(User, 700)
        ledger = (await session.scalars(select(CreditLedgerEntry))).all()
        assert gen.status == GenerationStatus.done
        assert gen.credits_spent == 76.0
        assert user.credits == 112.0
        assert len(ledger) == 1
        assert ledger[0].delta == 12.0


@pytest.mark.asyncio
async def test_postgres_finish_and_refund_race_never_double_credit(wan_pg_db):
    import asyncio

    factory = wan_pg_db
    url = "https://apixbotai.com/static/upload/provider-results/verified.mp4"
    async def finish():
        async with factory() as session:
            return await repo.finish_generation(
                session, 701, url, expected_task_id="neironych:wan-edit-701",
            )
    async def refund():
        async with factory() as session:
            return await repo.fail_generation_and_refund(
                session, 701, "Provider confirmed failure",
                expected_task_id="neironych:wan-edit-701",
                refund_note="pg_test:confirmed_failure",
            )
    await asyncio.wait_for(asyncio.gather(finish(), refund()), 20)
    async with factory() as session:
        gen = await session.get(Generation, 701)
        user = await session.get(User, 700)
        ledger = (await session.scalars(select(CreditLedgerEntry))).all()
        assert len(ledger) == 1
        if gen.status == GenerationStatus.done:
            assert user.credits == 112.0
            assert ledger[0].delta == 12.0
        else:
            assert gen.status == GenerationStatus.failed
            assert user.credits == 188.0
            assert ledger[0].delta == 88.0



@pytest.mark.asyncio
async def test_wan_duration_probe_rejects_remote_and_non_mp4(tmp_path, monkeypatch):
    from api import wan30_settlement

    # Price settlement must not fetch or trust an external user-controlled URL.
    with pytest.raises(ValueError, match="APIX-owned"):
        await wan30_settlement.probe_wan30_output_seconds(
            "https://remote.example.test/video.mp4",
        )
    fake_file = tmp_path / "fake.mp4"
    fake_file.write_bytes(b"<html>upstream temporary failure</html>")
    monkeypatch.setattr(
        wan30_settlement, "local_upload_path_from_url",
        lambda url: fake_file,
    )
    with pytest.raises(ValueError, match="verified MP4"):
        await wan30_settlement.probe_wan30_output_seconds(
            "https://apixbotai.com/static/upload/provider-results/fake.mp4",
        )


@pytest.mark.asyncio
async def test_wan_duration_probe_reads_verified_api_owned_mp4(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from api import wan30_settlement
    from api.media_gateway import MediaKind

    video = tmp_path / "owned.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32)
    monkeypatch.setattr(
        wan30_settlement, "local_upload_path_from_url",
        lambda url: video,
    )
    probe = AsyncMock(return_value=SimpleNamespace(
        width=1280, height=720, duration_seconds=5.038,
    ))
    monkeypatch.setattr(wan30_settlement, "probe_local_media", probe)
    assert await wan30_settlement.probe_wan30_output_seconds(
        "https://apixbotai.com/static/upload/provider-results/owned.mp4",
    ) == 5.038
    probe.assert_awaited_once_with(video, MediaKind.VIDEO)


@pytest_asyncio.fixture
async def wan_pg_prompt_db(wan_pg_db):
    """Submitted public prompt whose WAN reward must wait for the final charge."""
    factory = wan_pg_db
    async with factory() as session:
        session.add_all([
            User(id=800, tg_id=800, credits=0, referral_code="wan-author",
                 referrer_id=810, referrer_l2_id=820),
            User(id=810, tg_id=810, credits=0, referral_code="wan-author-l2"),
            User(id=820, tg_id=820, credits=0, referral_code="wan-author-l3"),
        ])
        await session.flush()
        session.add(UserPrompt(
            id=900, author_id=800, title="Recolor video",
            description="Video edit", category=PromptCategory.art,
            prompt_text="Recolor @Video1", tags=[],
            status=PromptStatus.approved, is_public=True, uses_count=1,
        ))
        gen = await session.get(Generation, 701)
        stored = json.loads(gen.input_params)
        stored["prompt_id"] = 900
        stored["wan30_billing"]["prompt_reward_deferred"] = True
        gen.input_params = json.dumps(stored)
        await session.commit()
    return factory


@pytest.mark.asyncio
async def test_postgres_deferred_wan_prompt_rewards_use_final_charge_once(wan_pg_prompt_db):
    import asyncio

    from db.prompt_repository import PROMPT_AUTHOR_SHARE, PROMPT_REF_L2_SHARE, PROMPT_REF_L3_SHARE

    factory = wan_pg_prompt_db
    url = "https://apixbotai.com/static/upload/provider-results/verified.mp4"

    async def notify():
        async with factory() as session:
            return await repo.finish_generation(
                session, 701, url, expected_task_id="neironych:wan-edit-701",
            )

    results = await asyncio.wait_for(asyncio.gather(*(notify() for _ in range(5))), 20)
    assert sum(x is not None for x in results) == 1
    async with factory() as session:
        generation = await session.get(Generation, 701)
        assert generation.credits_spent == 76.0  # Reserved 88, refunded 12
        billing = json.loads(generation.input_params)["wan30_billing"]
        assert billing["settled"] is True
        assert billing["prompt_rewards_settled"] is True
        amounts = billing["prompt_rewards"]
        expected = {
            "author": int(76 * PROMPT_AUTHOR_SHARE),
            "l2": int(76 * PROMPT_REF_L2_SHARE),
            "l3": int(76 * PROMPT_REF_L3_SHARE),
        }
        assert amounts == expected
        user_amounts = {700: 112.0, 800: expected["author"],
                        810: expected["l2"], 820: expected["l3"]}
        for user_id, expected_balance in user_amounts.items():
            assert (await session.get(User, user_id)).credits == expected_balance
        ledgers = (await session.scalars(select(CreditLedgerEntry))).all()
        assert len(ledgers) == 4
        assert {item.entry_type: item.delta for item in ledgers} == {
            "wan30_duration_refund": 12.0,
            "prompt_reward_author": float(expected["author"]),
            "prompt_reward_l2": float(expected["l2"]),
            "prompt_reward_l3": float(expected["l3"]),
        }
        assert {(item.entry_type, item.source_type, item.source_id)
                for item in ledgers} == {
                    ("wan30_duration_refund", "generation", "701"),
                    ("prompt_reward_author", "prompt", "900"),
                    ("prompt_reward_l2", "prompt", "900"),
                    ("prompt_reward_l3", "prompt", "900"),
                }
        assert all(
            "generation=701" in item.note
            for item in ledgers if item.entry_type.startswith("prompt_reward_")
        )


def test_wan_prompt_royalty_intent_is_durable_only_for_unsettled_prompt_quote():
    from api.miniapp_routes import _defer_wan_prompt_reward

    params = Wan30Quote(
        source_edit(), billable_seconds=22, rate=4.0, credits=88.0,
        resolution="720p",
    ).stored_params()
    assert _defer_wan_prompt_reward(params, prompt_id=900, is_wan=True)
    assert params["wan30_billing"]["prompt_reward_deferred"] is True

    for prompt_id, is_wan in ((None, True), (900, False)):
        other = Wan30Quote(
            source_edit(), billable_seconds=22, rate=4, credits=88,
            resolution="720p",
        ).stored_params()
        assert not _defer_wan_prompt_reward(other, prompt_id=prompt_id, is_wan=is_wan)
        assert "prompt_reward_deferred" not in other["wan30_billing"]
    fixed = {"wan30_billing": {"settled": True}}
    assert not _defer_wan_prompt_reward(fixed, prompt_id=900, is_wan=True)


@pytest.mark.asyncio
async def test_wan_prompt_use_at_submission_counts_without_paying(monkeypatch):
    from api.miniapp_routes import _mark_prompt_used_after_generation
    from db import prompt_repository

    recorder = AsyncMock()
    monkeypatch.setattr(prompt_repository, "use_prompt", recorder)
    await _mark_prompt_used_after_generation(
        object(), prompt_id=900, user_id=700, credits_spent=None,
    )
    recorder.assert_awaited_once()
    assert recorder.await_args.kwargs["credits_spent"] is None


@pytest.mark.asyncio
async def test_postgres_failed_wan_does_not_pay_deferred_prompt_rewards(wan_pg_prompt_db):
    async with wan_pg_prompt_db() as session:
        failed, refunded = await repo.fail_generation_and_refund(
            session, 701, "Provider rejected video",
            expected_task_id="neironych:wan-edit-701", refund_note="wan-prompt-failed",
        )
        assert failed and refunded == 88.0
    async with wan_pg_prompt_db() as session:
        assert (await session.get(Generation, 701)).status == GenerationStatus.failed
        assert (await session.get(User, 700)).credits == 188.0
        for uid in (800, 810, 820):
            assert (await session.get(User, uid)).credits == 0.0
        entries = (await session.scalars(select(CreditLedgerEntry))).all()
        assert len(entries) == 1
        assert entries[0].delta == 88.0


@pytest.mark.asyncio
async def test_postgres_deferred_wan_reward_failure_rolls_back_and_retries(
    wan_pg_prompt_db, monkeypatch,
):

    original_insert = repo._insert_credit_ledger

    async def reject_mid_reward(session, **values):
        if values.get("entry_type") == "prompt_reward_l2":
            raise RuntimeError("prompt reward journal unavailable")
        return await original_insert(session, **values)

    monkeypatch.setattr(repo, "_insert_credit_ledger", reject_mid_reward)
    url = "https://apixbotai.com/static/upload/provider-results/verified.mp4"
    async with wan_pg_prompt_db() as session:
        with pytest.raises(RuntimeError, match="reward journal unavailable"):
            await repo.finish_generation(
                session, 701, url, expected_task_id="neironych:wan-edit-701",
            )
        await session.rollback()

    async with wan_pg_prompt_db() as session:
        assert (await session.get(Generation, 701)).status == GenerationStatus.processing
        for uid, expected in ((700, 100.0), (800, 0.0), (810, 0.0), (820, 0.0)):
            assert (await session.get(User, uid)).credits == expected
        assert (await session.scalars(select(CreditLedgerEntry))).all() == []

    monkeypatch.setattr(repo, "_insert_credit_ledger", original_insert)
    async with wan_pg_prompt_db() as session:
        result = await repo.finish_generation(
            session, 701, url, expected_task_id="neironych:wan-edit-701",
        )
        assert result and result.credits_spent == 76
    async with wan_pg_prompt_db() as session:
        ledgers = (await session.scalars(select(CreditLedgerEntry))).all()
        assert len(ledgers) == 4


@pytest.mark.asyncio
async def test_postgres_wan_royalty_vs_failure_race_has_single_terminal_outcome(
    wan_pg_prompt_db,
):
    import asyncio

    url = "https://apixbotai.com/static/upload/provider-results/verified.mp4"

    async def complete():
        async with wan_pg_prompt_db() as session:
            return await repo.finish_generation(
                session, 701, url, expected_task_id="neironych:wan-edit-701",
            )

    async def fail():
        async with wan_pg_prompt_db() as session:
            return await repo.fail_generation_and_refund(
                session, 701, "Failed upstream", expected_task_id="neironych:wan-edit-701",
                refund_note="wan-royalty-race",
            )

    await asyncio.wait_for(asyncio.gather(complete(), fail()), timeout=20)
    async with wan_pg_prompt_db() as session:
        gen = await session.get(Generation, 701)
        entries = (await session.scalars(select(CreditLedgerEntry))).all()
        if gen.status == GenerationStatus.done:
            assert len(entries) == 4
            assert (await session.get(User, 700)).credits == 112.0
            assert (await session.get(User, 800)).credits == 22.0
        else:
            assert gen.status == GenerationStatus.failed
            assert len(entries) == 1
            assert (await session.get(User, 700)).credits == 188.0
            assert (await session.get(User, 800)).credits == 0.0


@pytest.mark.asyncio
async def test_postgres_fractional_settled_charge_does_not_mint_minimum_prompt_reward(
    wan_pg_prompt_db,
):
    from db.prompt_repository import apply_deferred_prompt_rewards

    async with wan_pg_prompt_db() as session:
        rewards = await apply_deferred_prompt_rewards(
            session, prompt_id=900, using_user_id=700,
            final_credits=0.5, generation_id=701,
        )
        assert rewards == {"author": 0, "l2": 0, "l3": 0}
        await session.commit()

    async with wan_pg_prompt_db() as session:
        for user_id in (800, 810, 820):
            assert (await session.get(User, user_id)).credits == 0.0
        assert (await session.scalars(select(CreditLedgerEntry))).all() == []
