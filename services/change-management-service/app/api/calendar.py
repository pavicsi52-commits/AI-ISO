"""Change calendar endpoints: maintenance windows and blackout periods."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import CalendarSvc
from app.models.enums import CalendarEntryKind
from app.schemas.change import (
    AvailabilityResponse,
    CalendarEntryCreateRequest,
    CalendarEntryResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/calendar", tags=["Change Calendar"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "",
    response_model=SuccessResponse[CalendarEntryResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a maintenance window or blackout period",
)
async def create_entry(
    organization_id: UUID, body: CalendarEntryCreateRequest, calendar: CalendarSvc
) -> SuccessResponse[CalendarEntryResponse]:
    """Create a calendar entry."""
    created = await calendar.create_entry(
        organization_id,
        kind=body.kind,
        title=body.title,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        description=body.description,
        timezone=body.timezone,
        recurrence=body.recurrence,
        recurrence_until=body.recurrence_until,
        is_org_wide=body.is_org_wide,
        capacity_limit=body.capacity_limit,
    )
    return SuccessResponse(
        meta=_meta(),
        data=CalendarEntryResponse.model_validate(created),
        message="Calendar entry created.",
    )


@router.get(
    "/{entry_id}",
    response_model=SuccessResponse[CalendarEntryResponse],
    summary="Read one calendar entry",
)
async def get_entry(
    organization_id: UUID, entry_id: UUID, calendar: CalendarSvc
) -> SuccessResponse[CalendarEntryResponse]:
    """One calendar entry."""
    found = await calendar.get(organization_id, entry_id)
    return SuccessResponse(
        meta=_meta(),
        data=CalendarEntryResponse.model_validate(found),
        message="Calendar entry read.",
    )


@router.get(
    "",
    response_model=SuccessResponse[list[CalendarEntryResponse]],
    summary="List calendar entries touching a range",
)
async def list_entries_in_range(
    organization_id: UUID,
    calendar: CalendarSvc,
    start: datetime,
    end: datetime,
    kind: Annotated[CalendarEntryKind | None, Query()] = None,
) -> SuccessResponse[list[CalendarEntryResponse]]:
    """Every entry with at least one occurrence touching a range."""
    pairs = await calendar.list_occurrences_in_range(
        organization_id, start=start, end=end, kind=kind
    )
    return SuccessResponse(
        meta=_meta(),
        data=[CalendarEntryResponse.model_validate(entry) for entry, _occurrences in pairs],
        message=f"{len(pairs)} entr(y/ies) in range.",
    )


@router.get(
    "/{entry_id}/availability",
    response_model=SuccessResponse[AvailabilityResponse],
    summary="Check a maintenance window's remaining capacity",
)
async def check_availability(
    organization_id: UUID,
    entry_id: UUID,
    calendar: CalendarSvc,
    exclude_change_id: Annotated[UUID | None, Query()] = None,
) -> SuccessResponse[AvailabilityResponse]:
    """Whether a window still has room for one more change."""
    result = await calendar.check_availability(
        organization_id, entry_id, exclude_change_id=exclude_change_id
    )
    return SuccessResponse(
        meta=_meta(),
        data=AvailabilityResponse(is_available=result.is_available, reason=result.reason),
        message="Availability checked.",
    )


__all__ = ["router"]
