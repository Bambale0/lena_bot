"""Repair impossible referral ancestry with immutable database audit evidence.

Dry-run is the default. Apply requires an explicit operator and deterministic
batch key; rerunning an applied batch is a read-only no-op.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Sequence

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.config import settings
from db.models import CreditLedgerEntry, ReferralCommissionLedger, User

MONEY = Decimal("0.01")
repair_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
RepairSessionLocal = async_sessionmaker(repair_engine, expire_on_commit=False)


@dataclass(frozen=True)
class InvalidEdge:
    user_id: int
    invalid_referrer_id: int


@dataclass(frozen=True)
class LineageChange:
    user_id: int
    old_refs: tuple[int | None, int | None, int | None]
    new_refs: tuple[int | None, int | None, int | None]
    reason: str


@dataclass(frozen=True)
class FinanceCorrection:
    transaction_id: int
    payer_user_id: int
    recipient_user_id: int
    level: int
    rate: float
    payment_amount_rub: float
    amount_rub: float


def _refs(user) -> tuple[int | None, int | None, int | None]:
    return (user.referrer_id, user.referrer_l2_id, user.referrer_l3_id)


def build_lineage_plan(users: Sequence[object]) -> tuple[list[InvalidEdge], list[LineageChange]]:
    by_id = {int(user.id): user for user in users}
    invalid_edges = sorted(
        (
            InvalidEdge(int(user.id), int(user.referrer_id))
            for user in users
            if user.referrer_id is not None
            and int(user.referrer_id) in by_id
            and user.created_at < by_id[int(user.referrer_id)].created_at
        ),
        key=lambda edge: edge.user_id,
    )
    invalid_roots = {edge.user_id for edge in invalid_edges}
    if not invalid_roots:
        return invalid_edges, []

    affected_ids = set(invalid_roots)
    for user in users:
        if user.referrer_id in invalid_roots or user.referrer_l2_id in invalid_roots:
            affected_ids.add(int(user.id))

    def direct_referrer(user_id: int) -> int | None:
        if user_id in invalid_roots:
            return None
        value = by_id[user_id].referrer_id
        return int(value) if value is not None and int(value) in by_id else None

    def canonical_refs(user_id: int) -> tuple[int | None, int | None, int | None]:
        result: list[int | None] = []
        seen = {user_id}
        current = direct_referrer(user_id)
        while current is not None and current not in seen and len(result) < 3:
            result.append(current)
            seen.add(current)
            current = direct_referrer(current)
        result.extend([None] * (3 - len(result)))
        return tuple(result[:3])  # type: ignore[return-value]

    changes: list[LineageChange] = []
    for user_id in sorted(affected_ids):
        old = _refs(by_id[user_id])
        new = canonical_refs(user_id)
        if old != new:
            changes.append(
                LineageChange(
                    user_id=user_id,
                    old_refs=old,
                    new_refs=new,
                    reason=(
                        "impossible_direct_referrer"
                        if user_id in invalid_roots
                        else "propagated_impossible_ancestry"
                    ),
                )
            )
    return invalid_edges, changes


def build_finance_plan(
    lineage_changes: Sequence[object], ledger_entries: Iterable[object]
) -> list[FinanceCorrection]:
    removed_at_level: dict[tuple[int, int], int] = {}
    for change in lineage_changes:
        for level, (old_recipient, new_recipient) in enumerate(
            zip(change.old_refs, change.new_refs), start=1
        ):
            if old_recipient is not None and old_recipient != new_recipient:
                if new_recipient is not None:
                    raise RuntimeError(
                        "Automatic referral finance repair cannot transfer commission "
                        f"payer={change.user_id} level={level} "
                        f"old_recipient={old_recipient} new_recipient={new_recipient}"
                    )
                removed_at_level[(int(change.user_id), level)] = int(old_recipient)

    grouped: dict[tuple[int, int, int, int], dict[str, Decimal | float]] = {}
    for entry in ledger_entries:
        expected_old = removed_at_level.get((int(entry.payer_user_id), int(entry.level)))
        if expected_old != int(entry.recipient_user_id):
            continue
        key = (
            int(entry.transaction_id),
            int(entry.payer_user_id),
            int(entry.recipient_user_id),
            int(entry.level),
        )
        item = grouped.setdefault(
            key,
            {
                "amount": Decimal("0"),
                "rate": float(entry.rate),
                "payment": float(entry.payment_amount_rub),
            },
        )
        item["amount"] = Decimal(item["amount"]) + Decimal(str(entry.amount_rub))

    corrections: list[FinanceCorrection] = []
    for key, values in sorted(grouped.items()):
        amount = Decimal(values["amount"]).quantize(MONEY, rounding=ROUND_HALF_UP)
        if amount <= 0:
            continue
        transaction_id, payer_user_id, recipient_user_id, level = key
        corrections.append(
            FinanceCorrection(
                transaction_id=transaction_id,
                payer_user_id=payer_user_id,
                recipient_user_id=recipient_user_id,
                level=level,
                rate=float(values["rate"]),
                payment_amount_rub=float(values["payment"]),
                amount_rub=float(amount),
            )
        )
    return corrections


def find_invalid_credit_bonuses(
    invalid_edges: Sequence[InvalidEdge],
    users: Sequence[object],
    credit_entries: Iterable[object],
) -> list[object]:
    by_id = {int(user.id): user for user in users}
    invalid_sources: dict[int, set[str]] = {}
    for edge in invalid_edges:
        child = by_id[edge.user_id]
        source_ids = {str(edge.user_id)}
        tg_id = int(getattr(child, "tg_id", 0) or 0)
        if tg_id > 0:
            source_ids.add(str(tg_id))
        invalid_sources.setdefault(edge.invalid_referrer_id, set()).update(source_ids)

    return [
        entry
        for entry in credit_entries
        if entry.entry_type in {"referral_first_topup_bonus", "referral_signup_bonus"}
        and float(entry.delta or 0) > 0
        and str(entry.source_id or "") in invalid_sources.get(int(entry.user_id), set())
    ]


async def _load_plan(session):
    users = list((await session.scalars(select(User).order_by(User.id))).all())
    invalid_edges, lineage_changes = build_lineage_plan(users)
    invalid_recipient_ids = sorted({edge.invalid_referrer_id for edge in invalid_edges})
    credit_entries: list[CreditLedgerEntry] = []
    if invalid_recipient_ids:
        credit_entries = list(
            (
                await session.scalars(
                    select(CreditLedgerEntry).where(
                        CreditLedgerEntry.user_id.in_(invalid_recipient_ids),
                        CreditLedgerEntry.entry_type.in_(
                            ["referral_first_topup_bonus", "referral_signup_bonus"]
                        ),
                    )
                )
            ).all()
        )
    invalid_credit_bonuses = find_invalid_credit_bonuses(
        invalid_edges, users, credit_entries
    )
    if invalid_credit_bonuses:
        entry_ids = sorted(int(entry.id) for entry in invalid_credit_bonuses)
        raise RuntimeError(
            "Automatic repair stopped: invalid referral credit bonuses require "
            f"a separately approved spent-credit correction; ledger_entry_ids={entry_ids}"
        )
    payer_ids = sorted({change.user_id for change in lineage_changes})
    ledger_entries: list[ReferralCommissionLedger] = []
    if payer_ids:
        ledger_entries = list(
            (
                await session.scalars(
                    select(ReferralCommissionLedger)
                    .where(ReferralCommissionLedger.payer_user_id.in_(payer_ids))
                    .order_by(ReferralCommissionLedger.id)
                )
            ).all()
        )
    return invalid_edges, lineage_changes, build_finance_plan(lineage_changes, ledger_entries)


def _summary(invalid_edges, lineage_changes, corrections) -> dict:
    invalid_commission = sum(Decimal(str(item.amount_rub)) for item in corrections)
    commission_by_recipient: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in corrections:
        commission_by_recipient[item.recipient_user_id] += Decimal(str(item.amount_rub))
    return {
        "invalid_edge_count": len(invalid_edges),
        "changed_user_count": len(lineage_changes),
        "lineage_change_counts": dict(
            sorted(Counter(item.reason for item in lineage_changes).items())
        ),
        "finance_correction_count": len(corrections),
        "invalid_commission_rub": float(invalid_commission.quantize(MONEY)),
        "invalid_commission_by_recipient": {
            str(recipient_id): float(amount.quantize(MONEY))
            for recipient_id, amount in sorted(commission_by_recipient.items())
        },
        "invalid_edges": [asdict(edge) for edge in invalid_edges],
    }


def _refund_key(batch_key: str, correction: FinanceCorrection) -> str:
    raw = (
        f"{batch_key}:{correction.transaction_id}:"
        f"{correction.recipient_user_id}:{correction.level}"
    )
    return "lineage:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


async def apply_repair(batch_key: str, operator: str, reason: str) -> dict:
    async with RepairSessionLocal() as session:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:batch_key, 0))"),
            {"batch_key": batch_key},
        )
        existing = (
            (
                await session.execute(
                    text(
                        "SELECT status, summary_json FROM referral_lineage_repair_batches "
                        "WHERE batch_key = :batch_key"
                    ),
                    {"batch_key": batch_key},
                )
            )
            .mappings()
            .first()
        )
        if existing:
            if existing["status"] != "applied":
                raise RuntimeError(f"Repair batch {batch_key!r} is not complete")
            return json.loads(existing["summary_json"] or "{}")

        # Hold a brief table-level write barrier so a registration or payment cannot
        # inherit the bad chain while the plan is being recomputed and committed.
        await session.execute(
            text(
                "LOCK TABLE transactions, users, credit_ledger, "
                "referral_commission_ledger IN EXCLUSIVE MODE"
            )
        )
        invalid_edges, lineage_changes, corrections = await _load_plan(session)
        base_summary = _summary(invalid_edges, lineage_changes, corrections)
        await session.execute(
            text(
                "INSERT INTO referral_lineage_repair_batches "
                "(batch_key, operator, reason, status, invalid_edge_count, changed_user_count, invalid_commission_rub) "
                "VALUES (:batch_key, :operator, :reason, 'applying', :edge_count, :user_count, :commission)"
            ),
            {
                "batch_key": batch_key,
                "operator": operator,
                "reason": reason,
                "edge_count": len(invalid_edges),
                "user_count": len(lineage_changes),
                "commission": base_summary["invalid_commission_rub"],
            },
        )
        await session.execute(
            text("SELECT set_config('apix.referral_repair_batch', :batch_key, true)"),
            {"batch_key": batch_key},
        )

        for change in lineage_changes:
            await session.execute(
                text(
                    "INSERT INTO referral_lineage_repair_rows "
                    "(batch_key,user_id,old_referrer_id,old_referrer_l2_id,old_referrer_l3_id,"
                    "new_referrer_id,new_referrer_l2_id,new_referrer_l3_id,reason) "
                    "VALUES (:batch_key,:user_id,:old1,:old2,:old3,:new1,:new2,:new3,:reason)"
                ),
                {
                    "batch_key": batch_key,
                    "user_id": change.user_id,
                    "old1": change.old_refs[0],
                    "old2": change.old_refs[1],
                    "old3": change.old_refs[2],
                    "new1": change.new_refs[0],
                    "new2": change.new_refs[1],
                    "new3": change.new_refs[2],
                    "reason": change.reason,
                },
            )
            await session.execute(
                update(User)
                .where(User.id == change.user_id)
                .values(
                    referrer_id=change.new_refs[0],
                    referrer_l2_id=change.new_refs[1],
                    referrer_l3_id=change.new_refs[2],
                )
            )

        recipients = sorted({item.recipient_user_id for item in corrections})
        balances: dict[int, Decimal] = {}
        if recipients:
            locked_recipients = list(
                (
                    await session.scalars(
                        select(User)
                        .where(User.id.in_(recipients))
                        .order_by(User.id)
                        .with_for_update()
                    )
                ).all()
            )
            balances = {
                int(user.id): Decimal(str(user.referral_balance or 0)).quantize(MONEY)
                for user in locked_recipients
            }

        balance_debit = Decimal("0")
        unrecovered = Decimal("0")
        for correction in corrections:
            amount = Decimal(str(correction.amount_rub)).quantize(MONEY)
            balance = balances[correction.recipient_user_id]
            debit = min(max(balance, Decimal("0")), amount)
            missing = amount - debit
            new_balance = balance - debit
            balances[correction.recipient_user_id] = new_balance
            balance_debit += debit
            unrecovered += missing
            await session.execute(
                update(User)
                .where(User.id == correction.recipient_user_id)
                .values(referral_balance=float(new_balance))
            )
            reversal = ReferralCommissionLedger(
                transaction_id=correction.transaction_id,
                payer_user_id=correction.payer_user_id,
                recipient_user_id=correction.recipient_user_id,
                level=correction.level,
                rate=correction.rate,
                payment_amount_rub=correction.payment_amount_rub,
                amount_rub=-float(amount),
                balance_after_rub=float(new_balance),
                event_type="reversal",
                refund_key=_refund_key(batch_key, correction),
            )
            session.add(reversal)
            await session.flush()
            await session.execute(
                text(
                    "INSERT INTO referral_finance_repair_rows "
                    "(batch_key,transaction_id,payer_user_id,recipient_user_id,level,amount_rub,"
                    "balance_debit_rub,unrecovered_rub,reversal_ledger_id) "
                    "VALUES (:batch_key,:tx,:payer,:recipient,:level,:amount,:debit,:missing,:ledger_id)"
                ),
                {
                    "batch_key": batch_key,
                    "tx": correction.transaction_id,
                    "payer": correction.payer_user_id,
                    "recipient": correction.recipient_user_id,
                    "level": correction.level,
                    "amount": float(amount),
                    "debit": float(debit),
                    "missing": float(missing),
                    "ledger_id": reversal.id,
                },
            )

        final_summary = {
            **base_summary,
            "batch_key": batch_key,
            "operator": operator,
            "balance_debit_rub": float(balance_debit.quantize(MONEY)),
            "unrecovered_rub": float(unrecovered.quantize(MONEY)),
        }
        await session.execute(
            text(
                "UPDATE referral_lineage_repair_batches SET status='applied', "
                "balance_debit_rub=:debit, unrecovered_rub=:missing, summary_json=:summary, "
                "applied_at=now() WHERE batch_key=:batch_key"
            ),
            {
                "batch_key": batch_key,
                "debit": final_summary["balance_debit_rub"],
                "missing": final_summary["unrecovered_rub"],
                "summary": json.dumps(final_summary, ensure_ascii=False, sort_keys=True),
            },
        )
        await session.commit()
        return final_summary


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="commit the audited repair")
    parser.add_argument("--batch-key", default="referral-lineage-20261028")
    parser.add_argument("--operator")
    parser.add_argument(
        "--reason",
        default="Remove referral ancestry attached after account creation",
    )
    args = parser.parse_args()
    if len(args.batch_key) > 64:
        parser.error("--batch-key must be at most 64 characters")
    if args.apply and not args.operator:
        parser.error("--operator is required with --apply")

    if args.apply:
        summary = await apply_repair(args.batch_key, args.operator, args.reason)
    else:
        async with RepairSessionLocal() as session:
            summary = _summary(*(await _load_plan(session)))
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    await repair_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
