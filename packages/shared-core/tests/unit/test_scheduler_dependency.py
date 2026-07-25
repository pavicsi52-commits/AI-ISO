"""Tests for dependency.py."""

from __future__ import annotations

import pytest
from shared_core.enums.job_status import JobStatus
from shared_core.scheduler.dependency import DependencyGraph, JobDependency
from shared_core.scheduler.exceptions import DependencyNotSatisfiedError


def test_is_satisfied_true_when_no_dependencies_registered() -> None:
    graph = DependencyGraph()

    assert graph.is_satisfied("job-b", lambda _job_id: None) is True


def test_is_satisfied_false_when_dependency_not_yet_completed() -> None:
    graph = DependencyGraph()
    graph.add(JobDependency(job_id="job-b", depends_on_job_id="job-a"))

    assert graph.is_satisfied("job-b", lambda _job_id: JobStatus.RUNNING) is False


def test_is_satisfied_true_once_dependency_completes() -> None:
    graph = DependencyGraph()
    graph.add(JobDependency(job_id="job-b", depends_on_job_id="job-a"))

    assert graph.is_satisfied("job-b", lambda _job_id: JobStatus.COMPLETED) is True


def test_is_satisfied_false_when_dependency_status_unknown() -> None:
    graph = DependencyGraph()
    graph.add(JobDependency(job_id="job-b", depends_on_job_id="job-a"))

    assert graph.is_satisfied("job-b", lambda _job_id: None) is False


def test_is_satisfied_honors_a_custom_condition() -> None:
    graph = DependencyGraph()
    graph.add(
        JobDependency(
            job_id="job-b",
            depends_on_job_id="job-a",
            condition=lambda status: status in (JobStatus.COMPLETED, JobStatus.FAILED),
        )
    )

    assert graph.is_satisfied("job-b", lambda _job_id: JobStatus.FAILED) is True


def test_require_satisfied_raises_when_unmet() -> None:
    graph = DependencyGraph()
    graph.add(JobDependency(job_id="job-b", depends_on_job_id="job-a"))

    with pytest.raises(DependencyNotSatisfiedError):
        graph.require_satisfied("job-b", lambda _job_id: JobStatus.RUNNING)


def test_require_satisfied_passes_silently_when_met() -> None:
    graph = DependencyGraph()
    graph.add(JobDependency(job_id="job-b", depends_on_job_id="job-a"))

    graph.require_satisfied("job-b", lambda _job_id: JobStatus.COMPLETED)


def test_parents_of_and_children_of_are_mirror_views() -> None:
    graph = DependencyGraph()
    graph.add(JobDependency(job_id="job-b", depends_on_job_id="job-a"))

    assert graph.parents_of("job-b") == frozenset({"job-a"})
    assert graph.children_of("job-a") == frozenset({"job-b"})


def test_dependencies_of_returns_the_registered_edges() -> None:
    graph = DependencyGraph()
    dependency = JobDependency(job_id="job-b", depends_on_job_id="job-a")
    graph.add(dependency)

    assert graph.dependencies_of("job-b") == frozenset({dependency})


def test_remove_job_drops_its_own_dependencies() -> None:
    graph = DependencyGraph()
    graph.add(JobDependency(job_id="job-b", depends_on_job_id="job-a"))

    graph.remove_job("job-b")

    assert graph.dependencies_of("job-b") == frozenset()


def test_remove_job_drops_edges_pointing_at_it() -> None:
    graph = DependencyGraph()
    graph.add(JobDependency(job_id="job-b", depends_on_job_id="job-a"))

    graph.remove_job("job-a")

    assert graph.parents_of("job-b") == frozenset()


def test_has_cycle_false_for_a_simple_chain() -> None:
    graph = DependencyGraph()
    graph.add(JobDependency(job_id="job-b", depends_on_job_id="job-a"))
    graph.add(JobDependency(job_id="job-c", depends_on_job_id="job-b"))

    assert graph.has_cycle() is False


def test_has_cycle_true_for_a_direct_cycle() -> None:
    graph = DependencyGraph()
    graph.add(JobDependency(job_id="job-a", depends_on_job_id="job-b"))
    graph.add(JobDependency(job_id="job-b", depends_on_job_id="job-a"))

    assert graph.has_cycle() is True


def test_has_cycle_true_for_an_indirect_cycle() -> None:
    graph = DependencyGraph()
    graph.add(JobDependency(job_id="job-a", depends_on_job_id="job-b"))
    graph.add(JobDependency(job_id="job-b", depends_on_job_id="job-c"))
    graph.add(JobDependency(job_id="job-c", depends_on_job_id="job-a"))

    assert graph.has_cycle() is True


def test_has_cycle_false_for_an_empty_graph() -> None:
    graph = DependencyGraph()

    assert graph.has_cycle() is False
