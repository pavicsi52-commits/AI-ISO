"""Regression tests for enum columns read back from the database.

Every enum-typed column in this service is annotated
``Mapped[SomeEnum]`` but stored in a plain ``String`` column. SQLAlchemy
therefore returns a raw ``str`` for any row actually loaded from
Postgres -- the annotation is a lie MyPy cannot catch, and an ``is``
comparison against an enum member is ``False`` for every such row.

``tests/test_engines.py`` deliberately needs no database and builds its
models in memory, where the attribute really is an enum. That is what
hid a live bug: recurring maintenance windows were silently demoted to
one-shot intervals, so alert suppression stopped at ``ends_at`` and
every later occurrence paged the on-call.

These tests round-trip through the real database so that behaviour is
exercised the way production actually sees it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_maintenance_window import AlertMaintenanceWindow
from app.models.enums import MaintenanceWindowScope, MaintenanceWindowType
from app.suppression.maintenance import is_window_active

STARTS_AT = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)
ENDS_AT = datetime(2026, 1, 1, 4, 0, tzinfo=UTC)


async def _persisted_window(
    db_session: AsyncSession,
    *,
    window_type: MaintenanceWindowType,
    recurrence_rule: str | None,
) -> AlertMaintenanceWindow:
    """Store a window, then force a genuine reload from Postgres."""
    window = AlertMaintenanceWindow(
        organization_id=uuid.uuid4(),
        name="nightly-patching",
        window_type=window_type,
        scope=MaintenanceWindowScope.ORGANIZATION,
        recurrence_rule=recurrence_rule,
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        enabled=True,
    )
    db_session.add(window)
    await db_session.flush()
    # Refreshing re-SELECTs the row, which is what makes the stored
    # (string) representation visible. ``expire()`` would defer the
    # load to attribute access, which cannot do async I/O.
    await db_session.refresh(window)
    return window


class TestMaintenanceWindowTypeRoundTrip:
    async def test_stored_window_type_really_is_a_plain_string(
        self, db_session: AsyncSession
    ) -> None:
        """Documents the root cause this whole module guards against."""
        window = await _persisted_window(
            db_session,
            window_type=MaintenanceWindowType.RECURRING,
            recurrence_rule="FREQ=DAILY",
        )
        assert not isinstance(window.window_type, MaintenanceWindowType)
        assert window.window_type == MaintenanceWindowType.RECURRING

    async def test_recurring_window_is_active_on_a_later_occurrence(
        self, db_session: AsyncSession
    ) -> None:
        """The live bug: this returned ``False`` for every stored window."""
        window = await _persisted_window(
            db_session,
            window_type=MaintenanceWindowType.RECURRING,
            recurrence_rule="FREQ=DAILY",
        )
        # Three days later, inside the same 02:00-04:00 slot.
        assert is_window_active(window, STARTS_AT + timedelta(days=3, minutes=30))

    async def test_recurring_window_is_inactive_outside_its_slot(
        self, db_session: AsyncSession
    ) -> None:
        window = await _persisted_window(
            db_session,
            window_type=MaintenanceWindowType.RECURRING,
            recurrence_rule="FREQ=DAILY",
        )
        assert not is_window_active(window, STARTS_AT + timedelta(days=3, hours=6))

    async def test_weekly_interval_is_honoured_after_a_round_trip(
        self, db_session: AsyncSession
    ) -> None:
        window = await _persisted_window(
            db_session,
            window_type=MaintenanceWindowType.RECURRING,
            recurrence_rule="FREQ=WEEKLY;INTERVAL=2",
        )
        assert is_window_active(window, STARTS_AT + timedelta(weeks=4, minutes=30))
        assert not is_window_active(window, STARTS_AT + timedelta(weeks=3, minutes=30))

    async def test_scheduled_window_still_expires_at_its_end(
        self, db_session: AsyncSession
    ) -> None:
        """The non-recurring path must stay one-shot."""
        window = await _persisted_window(
            db_session, window_type=MaintenanceWindowType.SCHEDULED, recurrence_rule=None
        )
        assert is_window_active(window, STARTS_AT + timedelta(hours=1))
        assert not is_window_active(window, STARTS_AT + timedelta(days=1))
