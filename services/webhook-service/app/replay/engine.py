"""Replay request validation (docs/057 "REPLAY").

A genuine gap -- no primitive for this exists in `shared_core`. Pure
validation only; actually finding and re-queuing the matched
deliveries is the service layer's own job, against the real database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.models.enums import ReplayScope


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    """The fields of a replay request this engine validates."""

    scope: ReplayScope
    event_id: str | None = None
    endpoint_id: str | None = None
    subscription_id: str | None = None
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None


_REQUIRED_FIELD_BY_SCOPE: dict[ReplayScope, str] = {
    ReplayScope.BY_EVENT: "event_id",
    ReplayScope.BY_ENDPOINT: "endpoint_id",
    ReplayScope.BY_SUBSCRIPTION: "subscription_id",
}


def validate_replay_request(request: ReplayRequest) -> list[str]:
    """Every validation error in *request*; an empty list means it is valid.

    ``BY_DATE_RANGE`` needs both bounds, with start strictly before end;
    every other scope needs its own single matching reference id set.
    """
    errors: list[str] = []
    if request.scope == ReplayScope.BY_DATE_RANGE:
        if request.date_range_start is None or request.date_range_end is None:
            errors.append("A date-range replay needs both date_range_start and date_range_end.")
        elif request.date_range_start >= request.date_range_end:
            errors.append("date_range_start must be strictly before date_range_end.")
        return errors

    required_field = _REQUIRED_FIELD_BY_SCOPE[request.scope]
    if getattr(request, required_field) is None:
        errors.append(f"A {request.scope.value} replay needs {required_field}.")
    return errors


__all__ = ["ReplayRequest", "validate_replay_request"]
