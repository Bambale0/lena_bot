from datetime import datetime, timezone

from core.reporting_time import moscow_day_bounds_utc


def test_moscow_day_bounds_use_midnight_msk_not_midnight_utc() -> None:
    now = datetime(2026, 9, 30, 21, 41, tzinfo=timezone.utc)

    start, end = moscow_day_bounds_utc(now)

    assert start == datetime(2026, 9, 30, 21, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc)


def test_moscow_day_bounds_keep_early_morning_inside_same_local_day() -> None:
    now = datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc)

    start, end = moscow_day_bounds_utc(now)

    assert start == datetime(2026, 9, 30, 21, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc)
