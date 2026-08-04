"""Detecting scheduling conflicts between two changes.

Pure -- no fixtures, no database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.conflicts.engine import ChangeWindow, detect_conflicts, windows_overlap
from app.models.enums import ConflictKind

_BASE = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def _window(
    start_offset_hours: float = 0,
    duration_hours: float = 2,
    *,
    assets: frozenset[str] = frozenset(),
    services: frozenset[str] = frozenset(),
    applications: frozenset[str] = frozenset(),
    dependencies: frozenset[str] = frozenset(),
) -> ChangeWindow:
    start = _BASE + timedelta(hours=start_offset_hours)
    return ChangeWindow(
        starts_at=start,
        ends_at=start + timedelta(hours=duration_hours),
        assets=assets,
        services=services,
        applications=applications,
        dependencies=dependencies,
    )


class TestWindowsOverlap:
    def test_identical_windows_overlap(self) -> None:
        a = _window()
        assert windows_overlap(a, a, slack=timedelta(0)) is True

    def test_disjoint_windows_do_not_overlap_with_no_slack(self) -> None:
        a = _window(0, 2)
        b = _window(5, 2)
        assert windows_overlap(a, b, slack=timedelta(0)) is False

    def test_back_to_back_windows_overlap_with_slack(self) -> None:
        a = _window(0, 2)
        b = _window(2, 2)
        assert windows_overlap(a, b, slack=timedelta(0)) is False
        assert windows_overlap(a, b, slack=timedelta(hours=1)) is True

    def test_partially_overlapping_windows_overlap(self) -> None:
        a = _window(0, 3)
        b = _window(2, 3)
        assert windows_overlap(a, b, slack=timedelta(0)) is True


class TestDetectConflicts:
    def test_non_overlapping_windows_have_no_conflicts(self) -> None:
        a = _window(0, 1, assets=frozenset({"host-1"}))
        b = _window(10, 1, assets=frozenset({"host-1"}))
        assert detect_conflicts(a, b, slack=timedelta(0)) == []

    def test_overlapping_windows_with_no_shared_resources_still_conflict_on_schedule(
        self,
    ) -> None:
        a = _window(0, 2)
        b = _window(1, 2)
        conflicts = detect_conflicts(a, b, slack=timedelta(0))
        assert conflicts == [ConflictKind.SCHEDULE]

    def test_shared_asset_within_overlapping_window_is_an_asset_conflict(self) -> None:
        a = _window(0, 2, assets=frozenset({"host-1"}))
        b = _window(1, 2, assets=frozenset({"host-1", "host-2"}))
        conflicts = detect_conflicts(a, b, slack=timedelta(0))
        assert ConflictKind.ASSET in conflicts

    def test_shared_service_within_overlapping_window_is_a_service_conflict(self) -> None:
        a = _window(0, 2, services=frozenset({"checkout"}))
        b = _window(1, 2, services=frozenset({"checkout"}))
        conflicts = detect_conflicts(a, b, slack=timedelta(0))
        assert ConflictKind.SERVICE in conflicts

    def test_shared_application_within_overlapping_window_is_an_application_conflict(self) -> None:
        a = _window(0, 2, applications=frozenset({"billing-api"}))
        b = _window(1, 2, applications=frozenset({"billing-api"}))
        conflicts = detect_conflicts(a, b, slack=timedelta(0))
        assert ConflictKind.APPLICATION in conflicts

    def test_shared_dependency_within_overlapping_window_is_a_dependency_conflict(self) -> None:
        a = _window(0, 2, dependencies=frozenset({"auth-service"}))
        b = _window(1, 2, dependencies=frozenset({"auth-service"}))
        conflicts = detect_conflicts(a, b, slack=timedelta(0))
        assert ConflictKind.DEPENDENCY in conflicts

    def test_disjoint_resources_produce_no_resource_conflicts(self) -> None:
        a = _window(0, 2, assets=frozenset({"host-1"}))
        b = _window(1, 2, assets=frozenset({"host-2"}))
        conflicts = detect_conflicts(a, b, slack=timedelta(0))
        assert conflicts == [ConflictKind.SCHEDULE]

    def test_shared_resources_but_no_overlap_produce_no_conflicts_at_all(self) -> None:
        a = _window(0, 1, assets=frozenset({"host-1"}))
        b = _window(20, 1, assets=frozenset({"host-1"}))
        assert detect_conflicts(a, b, slack=timedelta(0)) == []

    def test_multiple_resource_kinds_can_conflict_at_once(self) -> None:
        a = _window(
            0,
            2,
            assets=frozenset({"host-1"}),
            services=frozenset({"checkout"}),
        )
        b = _window(
            1,
            2,
            assets=frozenset({"host-1"}),
            services=frozenset({"checkout"}),
        )
        conflicts = detect_conflicts(a, b, slack=timedelta(0))
        assert ConflictKind.ASSET in conflicts
        assert ConflictKind.SERVICE in conflicts
