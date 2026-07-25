"""Schedule model.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "SCHEDULING TYPES":
Immediate, Scheduled Time, Cron Expression, Fixed Delay, Fixed Rate,
Calendar Schedule, Business Hours, Maintenance Window, Event Triggered.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from shared_core.scheduler.exceptions import InvalidScheduleError


class ScheduleType(StrEnum):
    """Every scheduling type docs/026 "SCHEDULING TYPES" names."""

    IMMEDIATE = "immediate"
    SCHEDULED_TIME = "scheduled_time"
    CRON_EXPRESSION = "cron_expression"
    FIXED_DELAY = "fixed_delay"
    FIXED_RATE = "fixed_rate"
    CALENDAR_SCHEDULE = "calendar_schedule"
    BUSINESS_HOURS = "business_hours"
    MAINTENANCE_WINDOW = "maintenance_window"
    EVENT_TRIGGERED = "event_triggered"


@dataclass(frozen=True, slots=True)
class Schedule:
    """One job's schedule configuration. Exactly the fields its ``schedule_type`` needs are set."""

    schedule_type: ScheduleType
    cron_expression: str | None = None
    run_at: datetime | None = None
    delay: timedelta | None = None
    interval: timedelta | None = None
    calendar_rule: str | None = None
    event_name: str | None = None

    def __post_init__(self) -> None:
        required_by_type: dict[ScheduleType, str] = {
            ScheduleType.SCHEDULED_TIME: "run_at",
            ScheduleType.CRON_EXPRESSION: "cron_expression",
            ScheduleType.FIXED_DELAY: "delay",
            ScheduleType.FIXED_RATE: "interval",
            ScheduleType.CALENDAR_SCHEDULE: "calendar_rule",
            ScheduleType.BUSINESS_HOURS: "calendar_rule",
            ScheduleType.EVENT_TRIGGERED: "event_name",
        }
        required_field = required_by_type.get(self.schedule_type)
        if required_field is not None and getattr(self, required_field) is None:
            raise InvalidScheduleError(
                f"Schedule type {self.schedule_type.value!r} requires {required_field!r}."
            )


__all__ = ["Schedule", "ScheduleType"]
