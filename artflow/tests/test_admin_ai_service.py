from __future__ import annotations

import pytest

from bot.services import admin_ai_service


@pytest.mark.asyncio
async def test_plans_add_credits() -> None:
    plan = await admin_ai_service.plan_action("начисли 50 бананов пользователю 123456789")

    assert plan["action"] == "add_credits"
    assert plan["params"] == {"telegram_id": 123456789, "amount": 50}
    assert plan["requires_confirmation"] is True


@pytest.mark.asyncio
async def test_plans_agent_report() -> None:
    plan = await admin_ai_service.plan_action("сделай отчёт по боту")

    assert [item["action"] for item in plan["actions"]] == [
        "stats",
        "maintenance_status",
        "list_promos",
        "analyze_logs",
    ]
    assert plan["requires_confirmation"] is False


@pytest.mark.asyncio
async def test_plans_research() -> None:
    plan = await admin_ai_service.plan_action("найди новые ИИ в генерации контента")

    assert plan["action"] == "research_ai"
    assert plan["requires_confirmation"] is False


@pytest.mark.asyncio
async def test_plans_generation_failures_as_log_analysis() -> None:
    plan = await admin_ai_service.plan_action("почему могли падать генерации?")

    assert plan["action"] == "analyze_logs"


@pytest.mark.asyncio
async def test_plans_create_promo_requires_confirmation() -> None:
    plan = await admin_ai_service.plan_action("создай промокод VIP20 скидка 20 лимит 100")

    assert plan["action"] == "create_promo"
    assert plan["params"] == {
        "code": "VIP20",
        "reward_type": "discount_percent",
        "value": 20,
        "max_uses": 100,
    }
    assert plan["requires_confirmation"] is True


def test_validate_unknown_is_not_executable() -> None:
    error = admin_ai_service.validate_plan({"action": "unknown", "summary": "Не понял"})

    assert error == "Не понял"


def test_validate_rejects_too_long_chain() -> None:
    plan = admin_ai_service.normalize_plan(
        {
            "action": "bot_report",
            "actions": [{"action": "stats", "params": {}} for _ in range(7)],
        }
    )

    assert "максимум" in (admin_ai_service.validate_plan(plan) or "")


def test_validate_mutating_action_cannot_disable_confirmation() -> None:
    plan = {
        "action": "ban_user",
        "params": {"telegram_id": 123456789},
        "requires_confirmation": False,
    }

    assert "требует подтверждения" in (admin_ai_service.validate_plan(plan) or "")
