"""Job dependencies.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "DEPENDENCIES": Run
After Job, Run Before Job, Conditional Execution, Workflow Dependencies,
Parent/Child Jobs, Dependency Graph. Purely in-process bookkeeping over
job ids -- this module does not itself execute anything;
:mod:`shared_core.scheduler.engine`/:mod:`~shared_core.scheduler.executor`
consult it to decide whether a job is currently eligible to run. "Run
Before Job" and "Workflow Dependencies" are the same directed edge
viewed from the other job/from a wider set of jobs, so neither needs a
distinct representation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from shared_core.enums.job_status import JobStatus
from shared_core.scheduler.exceptions import DependencyNotSatisfiedError

JobStatusLookup = Callable[[str], JobStatus | None]

_UNVISITED = 0
_VISITING = 1
_VISITED = 2


def _default_condition(status: JobStatus) -> bool:
    return status == JobStatus.COMPLETED


@dataclass(frozen=True, slots=True)
class JobDependency:
    """*job_id* may only run once *depends_on_job_id* satisfies *condition* ("Run After Job")."""

    job_id: str
    depends_on_job_id: str
    condition: Callable[[JobStatus], bool] = _default_condition


@dataclass(slots=True)
class DependencyGraph:
    """Tracks dependency edges between jobs and computes execution eligibility."""

    _edges: dict[str, set[JobDependency]] = field(default_factory=dict)

    def add(self, dependency: JobDependency) -> None:
        """Register a dependency edge ("Dependency Graph")."""
        self._edges.setdefault(dependency.job_id, set()).add(dependency)

    def remove_job(self, job_id: str) -> None:
        """Remove *job_id* entirely: its own dependencies, and any edge pointing at it."""
        self._edges.pop(job_id, None)
        for dependencies in self._edges.values():
            dependencies.difference_update(
                {d for d in dependencies if d.depends_on_job_id == job_id}
            )

    def dependencies_of(self, job_id: str) -> frozenset[JobDependency]:
        """Every dependency directly registered for *job_id*."""
        return frozenset(self._edges.get(job_id, set()))

    def parents_of(self, job_id: str) -> frozenset[str]:
        """The job ids *job_id* depends on ("Parent/Child Jobs")."""
        return frozenset(d.depends_on_job_id for d in self._edges.get(job_id, set()))

    def children_of(self, job_id: str) -> frozenset[str]:
        """The job ids that depend on *job_id* ("Run Before Job")."""
        return frozenset(
            dependent_id
            for dependent_id, dependencies in self._edges.items()
            if any(d.depends_on_job_id == job_id for d in dependencies)
        )

    def is_satisfied(self, job_id: str, status_lookup: JobStatusLookup) -> bool:
        """Whether every dependency of *job_id* is currently satisfied ("Conditional Execution")."""
        for dependency in self._edges.get(job_id, set()):
            status = status_lookup(dependency.depends_on_job_id)
            if status is None or not dependency.condition(status):
                return False
        return True

    def require_satisfied(self, job_id: str, status_lookup: JobStatusLookup) -> None:
        """Raise unless every dependency of *job_id* is currently satisfied.

        Raises:
            DependencyNotSatisfiedError: If any dependency is unmet.
        """
        if not self.is_satisfied(job_id, status_lookup):
            raise DependencyNotSatisfiedError(f"Job '{job_id}' has unsatisfied dependencies.")

    def has_cycle(self) -> bool:
        """Detect a dependency cycle via depth-first search ("Dependency Graph")."""
        color: dict[str, int] = dict.fromkeys(self._edges, _UNVISITED)

        def visit(node: str) -> bool:
            color[node] = _VISITING
            for dependency in self._edges.get(node, set()):
                neighbor = dependency.depends_on_job_id
                neighbor_color = color.get(neighbor, _UNVISITED)
                if neighbor_color == _VISITING:
                    return True
                if neighbor_color == _UNVISITED and visit(neighbor):
                    return True
            color[node] = _VISITED
            return False

        return any(color[node] == _UNVISITED and visit(node) for node in list(color))


__all__ = ["DependencyGraph", "JobDependency", "JobStatusLookup"]
