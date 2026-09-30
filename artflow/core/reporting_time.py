from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


REPORTING_TZ = ZoneInfo("Europe/Moscow")


def moscow_day_bounds_utc(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    local_now = current.astimezone(REPORTING_TZ)
    start_local = datetime.combine(local_now.date(), time.min, tzinfo=REPORTING_TZ)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
