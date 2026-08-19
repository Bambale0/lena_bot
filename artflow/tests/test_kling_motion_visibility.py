from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.kling_motion_visibility import KLING_30_MOTION, _ensure_required_rows


@pytest.mark.asyncio
async def test_required_kling_motion_rows_are_reactivated_and_backfilled() -> None:
    inactive_base = SimpleNamespace(model_key=KLING_30_MOTION, is_active=False)
    scalar_result = MagicMock()
    scalar_result.scalars.return_value.all.return_value = [inactive_base]

    session = AsyncMock()
    session.execute.return_value = scalar_result
    session.add = MagicMock()

    await _ensure_required_rows(session)

    assert inactive_base.is_active is True
    assert session.add.call_count == 2
    added_keys = {call.args[0].model_key for call in session.add.call_args_list}
    assert f"{KLING_30_MOTION}__resolution=720p" in added_keys
    assert f"{KLING_30_MOTION}__resolution=1080p" in added_keys
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_required_kling_motion_rows_do_not_write_when_already_active() -> None:
    rows = [
        SimpleNamespace(model_key=KLING_30_MOTION, is_active=True),
        SimpleNamespace(model_key=f"{KLING_30_MOTION}__resolution=720p", is_active=True),
        SimpleNamespace(model_key=f"{KLING_30_MOTION}__resolution=1080p", is_active=True),
    ]
    scalar_result = MagicMock()
    scalar_result.scalars.return_value.all.return_value = rows

    session = AsyncMock()
    session.execute.return_value = scalar_result
    session.add = MagicMock()

    await _ensure_required_rows(session)

    session.add.assert_not_called()
    session.commit.assert_not_awaited()
