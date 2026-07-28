"""Maintenance window recurrence evaluation ("MAINTENANCE WINDOWS"
"Support": Scheduled Windows, Recurring Windows, Emergency Windows).

A ``SCHEDULED``/``EMERGENCY`` window is in force exactly when its own
stored ``[starts_at, ends_at]`` interval contains the moment. A
``RECURRING`` window's stored interval is only its *first* occurrence;
whether it is in force now is a recurrence computation over that
occurrence's own duration and cadence, which is what this module owns.

``recurrence_rule`` accepts a deliberately small, explicit vocabulary
(``DAILY``/``WEEKLY``/``MONTHLY``, optionally ``;INTERVAL=<n>``) rather
than full RFC 5545 -- no RFC 5545 parser exists anywhere in
``packages/shared-core``, and pulling in a third-party one for the
handful of cadences a maintenance window realistically needs would add
a dependency this platform hasn't otherwise taken. An unrecognized
rule string is treated as *not* recurring (fail safe: a window that
cannot be interpreted never silently suppresses alerts forever).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.models.alert_maintenance_window import AlertMaintenanceWindow
from app.models.enums import MaintenanceWindowType

_MONTH_DAYS = 30
"""Approximation used for ``MONTHLY`` recurrence.

Calendar-exact month arithmetic (e.g. "the 31st" in a 30-day month)
needs a real calendar library this platform has not adopted; 30 days
is stated openly here rather than implied to be exact.
"""

_CADENCE_DAYS: dict[str, int] = {"DAILY": 1, "WEEKLY": 7, "MONTHLY": _MONTH_DAYS}


def _parse_recurrence(rule: str) -> timedelta | None:
    """Parse ``FREQ=DAILY``/``WEEKLY;INTERVAL=2``/... into a period.

    Returns ``None`` for anything unrecognized.
    """
    frequency: str | None = None
    interval = 1
    for part in rule.upper().replace(" ", "").split(";"):
        if not part:
            continue
        key, _, value = part.partition("=")
        if key == "FREQ":
            frequency = value
        elif key == "INTERVAL":
            if not value.isdigit() or int(value) < 1:
                return None
            interval = int(value)
    if frequency is None or frequency not in _CADENCE_DAYS:
        return None
    return timedelta(days=_CADENCE_DAYS[frequency] * interval)


def _is_recurring_active(window: AlertMaintenanceWindow, moment: datetime) -> bool:
    """Whether a ``RECURRING`` window's own repeating occurrence covers *moment*.

    Falls back to the single stored interval whenever the recurrence
    rule is absent or uninterpretable -- a window that cannot be
    interpreted must not silently suppress alerts forever.
    """
    duration = window.ends_at - window.starts_at
    if duration <= timedelta(0):
        return False
    period = _parse_recurrence(window.recurrence_rule) if window.recurrence_rule else None
    if period is None or period <= timedelta(0):
        return moment <= window.ends_at
    if duration >= period:
        # Each occurrence runs at least until the next one begins, so the
        # window is continuously in force from its own first start.
        return True
    return (moment - window.starts_at) % period < duration


def is_window_active(window: AlertMaintenanceWindow, moment: datetime) -> bool:
    """Return whether *window* is in force at *moment*."""
    if not window.enabled or moment < window.starts_at:
        return False
    if window.window_type is not MaintenanceWindowType.RECURRING:
        return moment <= window.ends_at
    return _is_recurring_active(window, moment)


__all__ = ["is_window_active"]
