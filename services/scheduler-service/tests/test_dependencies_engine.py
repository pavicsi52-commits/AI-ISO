"""Pure tests for app/dependencies/engine.py -- no database, no fixtures."""

from __future__ import annotations

import pytest
from shared_core.exceptions.validation import ValidationError

from app.dependencies.engine import (
    DependencyEdge,
    has_cycle,
    is_satisfied,
    require_acyclic,
    topological_order,
)
from app.models.enums import DependencyCondition, ExecutionStatus


class TestHasCycle:
    def test_no_edges_has_no_cycle(self) -> None:
        assert has_cycle([]) is False

    def test_a_simple_chain_has_no_cycle(self) -> None:
        edges = [DependencyEdge("a", "b"), DependencyEdge("b", "c")]
        assert has_cycle(edges) is False

    def test_a_direct_self_reference_is_a_cycle(self) -> None:
        assert has_cycle([DependencyEdge("a", "a")]) is True

    def test_an_indirect_cycle_is_detected(self) -> None:
        edges = [DependencyEdge("a", "b"), DependencyEdge("b", "c"), DependencyEdge("c", "a")]
        assert has_cycle(edges) is True

    def test_a_diamond_shape_is_not_a_cycle(self) -> None:
        edges = [
            DependencyEdge("a", "b"),
            DependencyEdge("a", "c"),
            DependencyEdge("b", "d"),
            DependencyEdge("c", "d"),
        ]
        assert has_cycle(edges) is False


class TestRequireAcyclic:
    def test_an_acyclic_graph_does_not_raise(self) -> None:
        require_acyclic([DependencyEdge("a", "b")])

    def test_a_cyclic_graph_raises(self) -> None:
        edges = [DependencyEdge("a", "b"), DependencyEdge("b", "a")]
        with pytest.raises(ValidationError):
            require_acyclic(edges)


class TestIsSatisfied:
    def test_a_parent_that_never_ran_never_satisfies(self) -> None:
        assert is_satisfied(condition=None, parent_latest_status=None) is False

    def test_default_condition_is_satisfied_by_a_completed_parent(self) -> None:
        assert is_satisfied(condition=None, parent_latest_status=ExecutionStatus.COMPLETED) is True

    def test_default_condition_is_not_satisfied_by_a_failed_parent(self) -> None:
        assert is_satisfied(condition=None, parent_latest_status=ExecutionStatus.FAILED) is False

    def test_on_success_requires_completed(self) -> None:
        assert (
            is_satisfied(
                condition=DependencyCondition.ON_SUCCESS,
                parent_latest_status=ExecutionStatus.COMPLETED,
            )
            is True
        )

    def test_on_failure_is_satisfied_by_a_failed_parent(self) -> None:
        assert (
            is_satisfied(
                condition=DependencyCondition.ON_FAILURE,
                parent_latest_status=ExecutionStatus.FAILED,
            )
            is True
        )

    def test_on_failure_is_not_satisfied_by_a_completed_parent(self) -> None:
        assert (
            is_satisfied(
                condition=DependencyCondition.ON_FAILURE,
                parent_latest_status=ExecutionStatus.COMPLETED,
            )
            is False
        )

    def test_on_completion_is_satisfied_by_any_terminal_status(self) -> None:
        for status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.SKIPPED,
        ):
            assert (
                is_satisfied(
                    condition=DependencyCondition.ON_COMPLETION, parent_latest_status=status
                )
                is True
            )

    def test_on_completion_is_not_satisfied_by_a_still_running_parent(self) -> None:
        assert (
            is_satisfied(
                condition=DependencyCondition.ON_COMPLETION,
                parent_latest_status=ExecutionStatus.RUNNING,
            )
            is False
        )


class TestTopologicalOrder:
    def test_a_parent_precedes_its_child(self) -> None:
        edges = [DependencyEdge("a", "b")]
        order = topological_order(edges, ["b", "a"])
        assert order.index("a") < order.index("b")

    def test_a_chain_orders_every_link(self) -> None:
        edges = [DependencyEdge("a", "b"), DependencyEdge("b", "c")]
        order = topological_order(edges, ["c", "b", "a"])
        assert order == ["a", "b", "c"]

    def test_independent_jobs_keep_their_relative_order(self) -> None:
        order = topological_order([], ["x", "y", "z"])
        assert order == ["x", "y", "z"]

    def test_a_diamond_orders_the_root_first_and_the_sink_last(self) -> None:
        edges = [
            DependencyEdge("a", "b"),
            DependencyEdge("a", "c"),
            DependencyEdge("b", "d"),
            DependencyEdge("c", "d"),
        ]
        order = topological_order(edges, ["d", "c", "b", "a"])
        assert order[0] == "a"
        assert order[-1] == "d"

    def test_a_cycle_raises_rather_than_returning_a_partial_order(self) -> None:
        edges = [DependencyEdge("a", "b"), DependencyEdge("b", "a")]
        with pytest.raises(ValidationError):
            topological_order(edges, ["a", "b"])

    def test_edges_naming_a_job_outside_the_given_set_are_ignored(self) -> None:
        edges = [DependencyEdge("outside", "a")]
        order = topological_order(edges, ["a"])
        assert order == ["a"]
