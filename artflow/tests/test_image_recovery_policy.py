from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from api.web import admin as web_admin
from core import image_recovery_policy
from db.models import ImageRecoveryPolicyAudit


@pytest.mark.asyncio
async def test_image_refund_sla_reads_database_before_environment(monkeypatch):
    session = SimpleNamespace(get=AsyncMock(return_value=None))
    monkeypatch.setattr(image_recovery_policy.settings, "IMAGE_AUTO_REFUND_SECONDS", 3600)
    fallback = await image_recovery_policy.get_image_recovery_policy(session, "nexus")
    assert (fallback.auto_refund_seconds, fallback.source) == (3600, "environment")
    session.get.return_value = SimpleNamespace(auto_refund_seconds=1800, updated_by_admin_tg_id=42)
    live = await image_recovery_policy.get_image_recovery_policy(session, "nexus")
    assert (live.auto_refund_seconds, live.source, live.updated_by_admin_tg_id) == (1800, "database", 42)


@pytest.mark.asyncio
async def test_image_refund_sla_admin_change_is_audited(monkeypatch):
    row = SimpleNamespace(auto_refund_seconds=3600, updated_by_admin_tg_id=None)
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[None, SimpleNamespace(scalar_one=lambda: row)]),
        add=MagicMock(), commit=AsyncMock(),
    )
    changed = await image_recovery_policy.set_image_recovery_policy(
        session, "neironych", 1800, admin_tg_id=42,
    )
    assert changed.auto_refund_seconds == 1800
    assert row.updated_by_admin_tg_id == 42
    audit = session.add.call_args.args[0]
    assert isinstance(audit, ImageRecoveryPolicyAudit)
    assert (audit.previous_seconds, audit.new_seconds, audit.changed_by_admin_tg_id) == (3600, 1800, 42)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_image_refund_sla_web_admin_requires_admin(monkeypatch):
    monkeypatch.setattr(web_admin.settings, "ADMIN_IDS", [42])
    body = web_admin.ImageRecoveryPolicyUpdate(auto_refund_seconds=1800)
    assert (await web_admin.admin_set_image_recovery_policy(
        "nexus", body, session=object(), user=None,
    )).status_code == 401
    assert (await web_admin.admin_set_image_recovery_policy(
        "nexus", body, session=object(), user=SimpleNamespace(tg_id=7),
    )).status_code == 403
    with pytest.raises(ValidationError):
        web_admin.ImageRecoveryPolicyUpdate(auto_refund_seconds=599)
