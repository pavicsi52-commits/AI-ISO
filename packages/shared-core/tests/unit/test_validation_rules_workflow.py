"""Tests for workflow validation rules."""

from __future__ import annotations

from shared_core.enums import Permission, Role
from shared_core.validation.base import ValidationSeverity
from shared_core.validation.rules import workflow


def test_check_circular_dependency_detects_a_cycle() -> None:
    result = workflow.check_circular_dependency(
        ["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")]
    )

    assert result.valid is False


def test_check_circular_dependency_passes_for_a_dag() -> None:
    result = workflow.check_circular_dependency(
        ["a", "b", "c"], [("a", "b"), ("a", "c"), ("b", "c")]
    )

    assert result.valid is True


def test_check_circular_dependency_passes_for_disconnected_nodes() -> None:
    result = workflow.check_circular_dependency(["a", "b"], [])

    assert result.valid is True


def test_check_circular_dependency_detects_self_loop() -> None:
    result = workflow.check_circular_dependency(["a"], [("a", "a")])

    assert result.valid is False


def test_check_infinite_loop_fails_without_max_iterations() -> None:
    result = workflow.check_infinite_loop([{"id": "loop-1"}])

    assert result.valid is False
    assert "loop-1" in result.errors[0]


def test_check_infinite_loop_fails_for_nonpositive_max_iterations() -> None:
    result = workflow.check_infinite_loop([{"id": "loop-1", "max_iterations": 0}])

    assert result.valid is False


def test_check_infinite_loop_passes_with_bounded_iterations() -> None:
    result = workflow.check_infinite_loop([{"id": "loop-1", "max_iterations": 10}])

    assert result.valid is True


def test_check_missing_node_detects_dangling_edge() -> None:
    result = workflow.check_missing_node(["a", "b"], [("a", "c")])

    assert result.valid is False
    assert "c" in result.errors[0]


def test_check_missing_node_passes_when_all_defined() -> None:
    result = workflow.check_missing_node(["a", "b"], [("a", "b")])

    assert result.valid is True


def test_check_invalid_transition_fails_for_disallowed_transition() -> None:
    result = workflow.check_invalid_transition(
        from_state="draft", to_state="published", allowed_transitions={"draft": {"review"}}
    )

    assert result.valid is False


def test_check_invalid_transition_passes_for_allowed_transition() -> None:
    result = workflow.check_invalid_transition(
        from_state="draft", to_state="review", allowed_transitions={"draft": {"review"}}
    )

    assert result.valid is True


def test_check_workflow_permission_passes_when_granted() -> None:
    result = workflow.check_workflow_permission(
        role=Role.OPERATOR, required_permission=Permission.EXECUTE
    )

    assert result.valid is True


def test_check_workflow_permission_fails_when_not_granted() -> None:
    result = workflow.check_workflow_permission(
        role=Role.VIEWER, required_permission=Permission.EXECUTE
    )

    assert result.valid is False


def test_check_required_inputs_fails_when_missing() -> None:
    result = workflow.check_required_inputs(provided={"a": 1}, required=["a", "b"])

    assert result.valid is False
    assert "b" in result.errors[0]


def test_check_required_inputs_passes_when_all_present() -> None:
    result = workflow.check_required_inputs(provided={"a": 1, "b": 2}, required=["a", "b"])

    assert result.valid is True


def test_check_workflow_timeout_fails_without_timeout() -> None:
    result = workflow.check_workflow_timeout(timeout_seconds=None, max_timeout_seconds=3600)

    assert result.valid is False


def test_check_workflow_timeout_fails_when_exceeding_max() -> None:
    result = workflow.check_workflow_timeout(timeout_seconds=7200, max_timeout_seconds=3600)

    assert result.valid is False


def test_check_workflow_timeout_passes_within_bounds() -> None:
    result = workflow.check_workflow_timeout(timeout_seconds=60, max_timeout_seconds=3600)

    assert result.valid is True


def test_check_rollback_support_warns_for_destructive_without_rollback() -> None:
    result = workflow.check_rollback_support(supports_rollback=False, is_destructive=True)

    assert result.valid is False
    assert result.severity == ValidationSeverity.WARNING


def test_check_rollback_support_passes_for_non_destructive() -> None:
    result = workflow.check_rollback_support(supports_rollback=False, is_destructive=False)

    assert result.valid is True


def test_check_rollback_support_passes_when_supported() -> None:
    result = workflow.check_rollback_support(supports_rollback=True, is_destructive=True)

    assert result.valid is True
