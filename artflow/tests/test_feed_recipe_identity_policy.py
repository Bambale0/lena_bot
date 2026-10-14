from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from api.web import admin as web_admin
from core import feed_recipe_identity_policy as policy
from db.models import FeedRecipeIdentityPolicyAudit

RULE = "Use the supplied user photos as the sole source of facial identity. Preserve the user's facial features across the final portrait."


@pytest.mark.asyncio
async def test_feed_identity_instruction_reads_required_database_row():
    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(instruction=RULE)))
    assert await policy.get_feed_recipe_identity_instruction(session) == RULE
    session.get.return_value = None
    with pytest.raises(RuntimeError, match="missing"):
        await policy.get_feed_recipe_identity_instruction(session)


@pytest.mark.asyncio
async def test_admin_identity_instruction_update_is_audited_even_at_same_initial_value():
    row = SimpleNamespace(instruction=RULE, updated_by_admin_tg_id=None)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: row)),
        add=MagicMock(), commit=AsyncMock(),
    )
    assert await policy.set_feed_recipe_identity_instruction(session, RULE, admin_tg_id=42) == RULE
    assert row.updated_by_admin_tg_id == 42
    audit = session.add.call_args.args[0]
    assert isinstance(audit, FeedRecipeIdentityPolicyAudit)
    assert (audit.previous_instruction, audit.new_instruction, audit.changed_by_admin_tg_id) == (RULE, RULE, 42)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_identity_instruction_admin_route_requires_admin(monkeypatch):
    monkeypatch.setattr(web_admin.settings, "ADMIN_IDS", [42])
    body = web_admin.FeedRecipeIdentityPolicyUpdate(instruction=RULE)
    assert (await web_admin.admin_set_feed_recipe_identity_policy(
        body, session=object(), user=None,
    )).status_code == 401
    assert (await web_admin.admin_set_feed_recipe_identity_policy(
        body, session=object(), user=SimpleNamespace(tg_id=7),
    )).status_code == 403
    with pytest.raises(ValidationError):
        web_admin.FeedRecipeIdentityPolicyUpdate(instruction="short")
    with pytest.raises(ValidationError):
        web_admin.FeedRecipeIdentityPolicyUpdate(instruction=" " * 120)


@pytest.mark.asyncio
async def test_identity_instruction_admin_route_passes_authenticated_actor(monkeypatch):
    monkeypatch.setattr(web_admin.settings, "ADMIN_IDS", [42])
    setter = AsyncMock(return_value=RULE)
    monkeypatch.setattr(web_admin, "set_feed_recipe_identity_instruction", setter)
    result = await web_admin.admin_set_feed_recipe_identity_policy(
        web_admin.FeedRecipeIdentityPolicyUpdate(instruction=RULE),
        session=object(), user=SimpleNamespace(tg_id=42),
    )
    assert result["data"]["instruction"] == RULE
    assert setter.await_args.kwargs["admin_tg_id"] == 42
