"""Missing media telemetry must never mutate generation or refund policy."""
from __future__ import annotations

from pathlib import Path

import pytest

from api import neironych_missing_media_telemetry as telemetry


@pytest.fixture(autouse=True)
def clear_process_cache():
    telemetry._last_logged.clear()
    yield
    telemetry._last_logged.clear()


def test_missing_media_one_error_per_generation_per_15_minutes():
    assert telemetry.should_log_missing_media(77, now=100.0)
    assert not telemetry.should_log_missing_media(77, now=101.0)
    assert telemetry.should_log_missing_media(78, now=101.0)
    assert not telemetry.should_log_missing_media(77, now=999.0)
    assert telemetry.should_log_missing_media(77, now=1000.0)


def test_missing_media_clock_rollback_still_logs():
    assert telemetry.should_log_missing_media(77, now=1000.0)
    assert telemetry.should_log_missing_media(77, now=999.0)


def test_missing_media_cache_stays_bounded():
    for i in range(telemetry.MAX_TRACKED_GENERATIONS + 50):
        assert telemetry.should_log_missing_media(i, now=100.0)
    assert len(telemetry._last_logged) <= telemetry.MAX_TRACKED_GENERATIONS


def test_missing_media_evicts_expired_entries():
    telemetry.should_log_missing_media(1, now=0.0)
    for i in range(2, telemetry.MAX_TRACKED_GENERATIONS + 1):
        telemetry.should_log_missing_media(i, now=900.0)
    assert telemetry.should_log_missing_media(telemetry.MAX_TRACKED_GENERATIONS + 1, now=901.0)
    assert 1 not in telemetry._last_logged


def test_payment_refund_and_result_recovery_paths_untouched():
    source = (Path(__file__).parents[1] / "api/miniapp_routes.py").read_text()
    assert 'return await refund_if_overdue("completed_no_media")' in source
    assert 'if should_log_missing_media(gen.id):' in source
    assert "request_id=%s" not in source[source.index("if should_log_missing_media(gen.id):"):][:280]
