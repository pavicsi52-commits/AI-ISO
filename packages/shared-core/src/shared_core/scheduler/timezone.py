"""Timezone support.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "TIMEZONE SUPPORT":
UTC, Organization Timezone, Project Timezone, User Timezone, Automatic
DST handling, Timezone conversion. Built entirely on the stdlib
:mod:`zoneinfo` (IANA tz database) -- DST handling is automatic by
construction, not something this module implements itself.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared_core.scheduler.exceptions import InvalidScheduleError


def validate_timezone(name: str) -> None:
    """Ensure *name* is a valid IANA timezone name.

    Raises:
        InvalidScheduleError: If *name* isn't a recognized timezone.
    """
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidScheduleError(f"{name!r} is not a valid timezone.") from exc


def localize(moment: datetime, timezone_name: str) -> datetime:
    """Attach *timezone_name* to a naive *moment* (interpreting it as local wall-clock time)."""
    validate_timezone(timezone_name)
    return moment.replace(tzinfo=ZoneInfo(timezone_name))


def to_utc(moment: datetime, timezone_name: str) -> datetime:
    """Convert *moment* (naive or aware) to UTC, interpreting a naive value as *timezone_name*."""
    if moment.tzinfo is None:
        moment = localize(moment, timezone_name)
    return moment.astimezone(UTC)


def convert_timezone(moment: datetime, *, to: str) -> datetime:
    """Convert an aware *moment* to the wall-clock time in timezone *to* ("Timezone conversion")."""
    validate_timezone(to)
    if moment.tzinfo is None:
        raise InvalidScheduleError("convert_timezone requires a timezone-aware datetime.")
    return moment.astimezone(ZoneInfo(to))


__all__ = ["convert_timezone", "localize", "to_utc", "validate_timezone"]
