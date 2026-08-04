"""Fingerprint correlation, the lifecycle transition graph, and MTTA/MTTR."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from shared_core.exceptions.validation import ValidationError

from app.incidents.engine import (
    ALLOWED_TRANSITIONS,
    compute_durations,
    correlates,
    fingerprint,
    is_reopen,
    percentile,
    validate_transition,
)
from app.models.enums import TERMINAL_INCIDENT_STATUSES, IncidentStatus


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 3, hour, minute, tzinfo=UTC)


class TestFingerprint:
    def test_the_same_inputs_produce_the_same_fingerprint(self) -> None:
        first = fingerprint(source="monitoring", category="database", key="host-1")
        second = fingerprint(source="monitoring", category="database", key="host-1")
        assert first == second

    def test_a_different_key_produces_a_different_fingerprint(self) -> None:
        base = fingerprint(source="monitoring", category="database", key="host-1")
        assert base != fingerprint(source="monitoring", category="database", key="host-2")

    def test_a_different_source_produces_a_different_fingerprint(self) -> None:
        base = fingerprint(source="monitoring", category="database", key="host-1")
        assert base != fingerprint(source="alerting", category="database", key="host-1")


class TestCorrelates:
    def test_matching_fingerprints_within_the_window_correlate(self) -> None:
        assert (
            correlates(
                existing_fingerprint="fp",
                new_fingerprint="fp",
                existing_status=IncidentStatus.INVESTIGATING,
                existing_last_activity=at(10),
                now=at(10, 10),
                window_minutes=15,
            )
            is True
        )

    def test_different_fingerprints_never_correlate(self) -> None:
        assert (
            correlates(
                existing_fingerprint="fp-a",
                new_fingerprint="fp-b",
                existing_status=IncidentStatus.NEW,
                existing_last_activity=at(10),
                now=at(10, 1),
            )
            is False
        )

    def test_a_closed_incident_never_correlates(self) -> None:
        # A recurrence after closure is a new occurrence of an old
        # problem, not a continuation of the resolved one.
        assert (
            correlates(
                existing_fingerprint="fp",
                new_fingerprint="fp",
                existing_status=IncidentStatus.CLOSED,
                existing_last_activity=at(10),
                now=at(10, 1),
            )
            is False
        )

    def test_a_resolved_incident_never_correlates(self) -> None:
        # RESOLVED is not in TERMINAL_INCIDENT_STATUSES but must still
        # refuse correlation -- it is not open work either.
        assert IncidentStatus.RESOLVED not in TERMINAL_INCIDENT_STATUSES
        assert (
            correlates(
                existing_fingerprint="fp",
                new_fingerprint="fp",
                existing_status=IncidentStatus.RESOLVED,
                existing_last_activity=at(10),
                now=at(10, 1),
            )
            is False
        )

    def test_outside_the_window_does_not_correlate(self) -> None:
        assert (
            correlates(
                existing_fingerprint="fp",
                new_fingerprint="fp",
                existing_status=IncidentStatus.NEW,
                existing_last_activity=at(10),
                now=at(10, 30),
                window_minutes=15,
            )
            is False
        )

    def test_exactly_at_the_window_edge_still_correlates(self) -> None:
        assert (
            correlates(
                existing_fingerprint="fp",
                new_fingerprint="fp",
                existing_status=IncidentStatus.NEW,
                existing_last_activity=at(10),
                now=at(10, 15),
                window_minutes=15,
            )
            is True
        )

    @pytest.mark.parametrize("status", sorted(TERMINAL_INCIDENT_STATUSES, key=str))
    def test_every_terminal_status_refuses_correlation(self, status: IncidentStatus) -> None:
        assert (
            correlates(
                existing_fingerprint="fp",
                new_fingerprint="fp",
                existing_status=status,
                existing_last_activity=at(10),
                now=at(10, 1),
            )
            is False
        )


class TestLifecycleTransitions:
    def test_new_can_move_to_assigned(self) -> None:
        validate_transition(IncidentStatus.NEW, IncidentStatus.ASSIGNED)

    def test_new_cannot_jump_to_resolved(self) -> None:
        with pytest.raises(ValidationError, match="cannot move to"):
            validate_transition(IncidentStatus.NEW, IncidentStatus.RESOLVED)

    def test_resolved_can_move_back_to_investigating(self) -> None:
        # The reopen path: the fix did not hold.
        validate_transition(IncidentStatus.RESOLVED, IncidentStatus.INVESTIGATING)

    def test_closed_can_still_reopen(self) -> None:
        validate_transition(IncidentStatus.CLOSED, IncidentStatus.INVESTIGATING)

    def test_cancelled_is_a_true_dead_end(self) -> None:
        assert ALLOWED_TRANSITIONS[IncidentStatus.CANCELLED] == frozenset()
        with pytest.raises(ValidationError):
            validate_transition(IncidentStatus.CANCELLED, IncidentStatus.NEW)

    def test_merged_is_a_true_dead_end(self) -> None:
        assert ALLOWED_TRANSITIONS[IncidentStatus.MERGED] == frozenset()

    def test_every_status_has_a_transition_table_entry(self) -> None:
        # A status present in the enum but missing from the table would
        # KeyError the first time it was ever validated against.
        for status in IncidentStatus:
            assert status in ALLOWED_TRANSITIONS

    def test_the_error_names_what_is_actually_allowed(self) -> None:
        with pytest.raises(ValidationError, match="Allowed from here"):
            validate_transition(IncidentStatus.NEW, IncidentStatus.CLOSED)


class TestIsReopen:
    def test_resolved_to_investigating_is_a_reopen(self) -> None:
        assert is_reopen(IncidentStatus.RESOLVED, IncidentStatus.INVESTIGATING) is True

    def test_closed_to_investigating_is_a_reopen(self) -> None:
        assert is_reopen(IncidentStatus.CLOSED, IncidentStatus.INVESTIGATING) is True

    def test_new_to_assigned_is_not_a_reopen(self) -> None:
        assert is_reopen(IncidentStatus.NEW, IncidentStatus.ASSIGNED) is False

    def test_resolved_to_closed_is_not_a_reopen(self) -> None:
        assert is_reopen(IncidentStatus.RESOLVED, IncidentStatus.CLOSED) is False


class TestDurationMetrics:
    def test_mtta_and_mttr_are_none_before_their_moments(self) -> None:
        result = compute_durations(detected_at=at(10), acknowledged_at=None, resolved_at=None)
        assert result.mtta_seconds is None
        assert result.mttr_seconds is None

    def test_mtta_is_never_zero_for_an_unacknowledged_incident(self) -> None:
        # A zero would read as "acknowledged instantly," the opposite of
        # "not yet known."
        result = compute_durations(detected_at=at(10), acknowledged_at=None, resolved_at=None)
        assert result.mtta_seconds != 0.0

    def test_mtta_and_mttr_compute_correctly_once_known(self) -> None:
        result = compute_durations(
            detected_at=at(10), acknowledged_at=at(10, 5), resolved_at=at(11)
        )
        assert result.mtta_seconds == 300.0
        assert result.mttr_seconds == 3_600.0


class TestPercentile:
    def test_empty_is_none(self) -> None:
        assert percentile([], pct=90) is None

    def test_p90_of_ten_values_is_nearest_rank(self) -> None:
        values = [float(one) for one in range(1, 11)]  # 1..10
        assert percentile(values, pct=90) == 9.0

    def test_a_single_value_is_its_own_percentile(self) -> None:
        assert percentile([42.0], pct=50) == 42.0

    def test_an_out_of_range_percentile_is_refused(self) -> None:
        with pytest.raises(ValueError, match="pct must be"):
            percentile([1.0, 2.0], pct=0)
        with pytest.raises(ValueError, match="pct must be"):
            percentile([1.0, 2.0], pct=101)

    def test_the_result_always_names_an_actual_value(self) -> None:
        # Nearest-rank, not interpolated: the result must be a member of
        # the input, not a number between two of them.
        values = [10.0, 20.0, 30.0]
        assert percentile(values, pct=50) in values
