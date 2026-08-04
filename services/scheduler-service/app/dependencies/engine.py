"""Dependency graph: circular detection and execution ordering.

**Cycle detection reuses ``shared_core.scheduler.dependency.DependencyGraph``
directly** rather than reimplementing depth-first search a second time --
its own ``condition`` callable operates on
:class:`shared_core.enums.job_status.JobStatus`, a different, coarser
enum than this service's own :class:`~app.models.enums.DependencyCondition`
(``ON_SUCCESS``/``ON_FAILURE``/``ON_COMPLETION``), so :func:`is_satisfied`
below is this service's own small addition rather than a second call
into the shared graph -- the structural cycle check is the part that
translates cleanly and is reused; the richer condition semantics this
service's own ``job_dependencies`` table supports are not something the
shared framework's generic single-condition model expresses.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from shared_core.exceptions.validation import ValidationError
from shared_core.scheduler.dependency import DependencyGraph
from shared_core.scheduler.dependency import JobDependency as SharedJobDependency

from app.models.enums import DependencyCondition, ExecutionStatus


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    """One ``parent -> child`` edge, decoupled from the ORM row."""

    parent_job_id: str
    child_job_id: str


def has_cycle(edges: list[DependencyEdge]) -> bool:
    """Whether *edges* contains a circular dependency.

    Delegates entirely to :class:`shared_core.scheduler.dependency
    .DependencyGraph`'s own depth-first search.
    """
    graph = DependencyGraph()
    for edge in edges:
        graph.add(
            SharedJobDependency(job_id=edge.child_job_id, depends_on_job_id=edge.parent_job_id)
        )
    return graph.has_cycle()


def require_acyclic(edges: list[DependencyEdge]) -> None:
    """Confirm *edges* contains no circular dependency.

    Raises:
        ValidationError: If it does.
    """
    if has_cycle(edges):
        raise ValidationError(
            "This dependency would create a circular chain -- a job cannot, "
            "even indirectly, depend on itself."
        )


_SATISFYING_STATUSES: dict[DependencyCondition, frozenset[ExecutionStatus]] = {
    DependencyCondition.ON_SUCCESS: frozenset({ExecutionStatus.COMPLETED}),
    DependencyCondition.ON_FAILURE: frozenset({ExecutionStatus.FAILED, ExecutionStatus.TIMED_OUT}),
    DependencyCondition.ON_COMPLETION: frozenset(
        {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMED_OUT,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.SKIPPED,
            ExecutionStatus.RECOVERED,
        }
    ),
}


def is_satisfied(
    *, condition: DependencyCondition | None, parent_latest_status: ExecutionStatus | None
) -> bool:
    """Whether one dependency edge is currently satisfied.

    ``condition is None`` (a plain ``SEQUENTIAL``/``PARALLEL`` edge, not
    ``CONDITIONAL``) is satisfied by the parent's latest execution simply
    having completed successfully -- the same default a
    ``SEQUENTIAL``/``PARALLEL`` edge's own docs/054 definition implies. A
    parent that has never run yet (``parent_latest_status is None``)
    never satisfies anything -- there is no evidence to satisfy it with.
    """
    if parent_latest_status is None:
        return False
    effective_condition = condition or DependencyCondition.ON_SUCCESS
    return parent_latest_status in _SATISFYING_STATUSES[effective_condition]


def topological_order(edges: list[DependencyEdge], job_ids: list[str]) -> list[str]:
    """Every job id in *job_ids*, ordered so each parent precedes its children.

    Kahn's algorithm -- not part of ``shared_core.scheduler.dependency``,
    whose own ``DependencyGraph`` exposes cycle detection and per-job
    parent/child lookup but no whole-graph ordering. Ties (jobs with no
    remaining unresolved dependency between them) preserve *job_ids*'s
    own relative order, so the result is deterministic given the same
    input.

    Raises:
        ValidationError: If *edges* contains a cycle -- there is no
            valid order to return.
    """
    require_acyclic(edges)

    in_degree: dict[str, int] = dict.fromkeys(job_ids, 0)
    children_of: dict[str, list[str]] = {job_id: [] for job_id in job_ids}
    for edge in edges:
        if edge.parent_job_id not in children_of or edge.child_job_id not in in_degree:
            continue
        children_of[edge.parent_job_id].append(edge.child_job_id)
        in_degree[edge.child_job_id] += 1

    queue: deque[str] = deque(job_id for job_id in job_ids if in_degree[job_id] == 0)
    ordered: list[str] = []
    while queue:
        current = queue.popleft()
        ordered.append(current)
        for child in children_of[current]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
    return ordered


__all__ = [
    "DependencyEdge",
    "has_cycle",
    "is_satisfied",
    "require_acyclic",
    "topological_order",
]
