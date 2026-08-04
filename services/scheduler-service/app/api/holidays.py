"""Holiday calendar entries."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import HolidaySvc
from app.models.holiday import HolidayCalendarEntry
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.scheduler import HolidayCreateRequest, HolidayResponse

router = APIRouter(prefix="/scheduler/holidays", tags=["Holidays"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _falls_in(entry: HolidayCalendarEntry, *, year: int) -> date:
    """The date *entry* would fall on within *year*.

    A recurring Feb 29 has no such date in a non-leap year -- clamped to
    Feb 28, the same non-fatal fallback
    ``HolidayCalendarRepository.to_dates`` uses, so this can never raise
    for a value that repository would simply omit.
    """
    if not entry.is_recurring:
        return entry.holiday_date
    try:
        return entry.holiday_date.replace(year=year)
    except ValueError:
        return entry.holiday_date.replace(year=year, day=28)


@router.post(
    "",
    response_model=SuccessResponse[HolidayResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Define a holiday",
)
async def create_holiday(
    organization_id: UUID, body: HolidayCreateRequest, holidays: HolidaySvc
) -> SuccessResponse[HolidayResponse]:
    """Define a holiday."""
    created = await holidays.create_holiday(
        organization_id,
        name=body.name,
        holiday_date=body.holiday_date,
        scope=body.scope,
        scope_id=body.scope_id,
        is_recurring=body.is_recurring,
        description=body.description,
    )
    return SuccessResponse(
        meta=_meta(), data=HolidayResponse.model_validate(created), message="Holiday created."
    )


@router.get("", response_model=SuccessResponse[list[HolidayResponse]], summary="List holidays")
async def list_holidays(
    organization_id: UUID,
    holidays: HolidaySvc,
    year: Annotated[int | None, Query(ge=1970, le=2200)] = None,
) -> SuccessResponse[list[HolidayResponse]]:
    """Every holiday this organization has defined, or only those covering *year* if given."""
    entries = await holidays.list_holidays(organization_id)
    if year is None:
        rows = entries
    else:
        dates = await holidays.dates_for_year(organization_id, year=year)
        rows = [one for one in entries if _falls_in(one, year=year) in dates]
    return SuccessResponse(
        meta=_meta(),
        data=[HolidayResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} holiday(s).",
    )


@router.delete("/{holiday_id}", response_model=SuccessResponse[None], summary="Remove a holiday")
async def delete_holiday(
    organization_id: UUID, holiday_id: UUID, holidays: HolidaySvc
) -> SuccessResponse[None]:
    """Remove a holiday."""
    await holidays.delete(organization_id, holiday_id)
    return SuccessResponse(meta=_meta(), data=None, message="Holiday removed.")


__all__ = ["router"]
