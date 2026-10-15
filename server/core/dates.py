"""
Day boundaries in the site time zone (Africa/Lagos), computed in Python.

Never filter with Django's `__date` / `Trunc*` lookups: on MySQL/MariaDB they call
CONVERT_TZ() with a named zone, which returns NULL when the server's time-zone
tables aren't loaded (the norm on cPanel hosts), silently matching nothing.
Filter with `field__gte=day_start(d), field__lt=day_start(d + 1 day)` instead.
"""
from datetime import date, datetime, time, timedelta

from django.utils import timezone


def day_start(d: date) -> datetime:
    """Aware datetime for 00:00 on `d` in the current time zone."""
    return timezone.make_aware(datetime.combine(d, time.min), timezone.get_current_timezone())


def day_range(first: date, last: date) -> tuple[datetime, datetime]:
    """(start, end_exclusive) covering whole days `first`..`last` inclusive."""
    return day_start(first), day_start(last + timedelta(days=1))


def parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
