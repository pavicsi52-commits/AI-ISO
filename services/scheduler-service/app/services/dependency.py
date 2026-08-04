"""Job dependency management: edges, cycle prevention, and readiness checks."""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.dependencies.engine import DependencyEdge, is_satisfied, require_acyclic
from app.models.dependency import JobDependency
from app.models.enums import DependencyCondition, DependencyType, execution_status_of
from app.repositories.dependency import JobDependencyRepository
from app.repositories.execution import JobExecutionRepository
from app.repositories.job import ScheduledJobRepository


class DependencyService:
    """Dependency edges between jobs, and whether a job is currently eligible to run."""

    def __init__(
        self,
        dependencies: JobDependencyRepository,
        jobs: ScheduledJobRepository,
        executions: JobExecutionRepository,
    ) -> None:
        self._dependencies = dependencies
        self._jobs = jobs
        self._executions = executions

    async def add_dependency(
        self,
        organization_id: UUID,
        *,
        parent_job_id: UUID,
        child_job_id: UUID,
        dependency_type: DependencyType = DependencyType.SEQUENTIAL,
        condition: DependencyCondition | None = None,
    ) -> JobDependency:
        """Register *child_job_id* as depending on *parent_job_id*.

        Raises:
            NotFoundError: If either job does not exist here.
            ValidationError: If this edge would create a circular chain,
                or a job is made to depend on itself.
        """
        if parent_job_id == child_job_id:
            raise ValidationError("A job cannot depend on itself.")
        await self._jobs.require_in_org(organization_id, parent_job_id)
        await self._jobs.require_in_org(organization_id, child_job_id)

        existing = await self._dependencies.list_for_org(organization_id)
        edges = [DependencyEdge(str(one.parent_job_id), str(one.child_job_id)) for one in existing]
        edges.append(DependencyEdge(str(parent_job_id), str(child_job_id)))
        require_acyclic(edges)

        return await self._dependencies.create(
            JobDependency(
                organization_id=organization_id,
                parent_job_id=parent_job_id,
                child_job_id=child_job_id,
                dependency_type=dependency_type,
                condition=condition,
            )
        )

    async def remove(self, organization_id: UUID, dependency_id: UUID) -> None:
        """Remove a dependency edge.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stored = await self._dependencies.require_in_org(organization_id, dependency_id)
        await self._dependencies.delete(stored)

    async def list_for_job(self, organization_id: UUID, job_id: UUID) -> list[JobDependency]:
        """Every dependency naming this job as the dependent (child) side."""
        return await self._dependencies.list_parents_of(organization_id, job_id)

    async def is_ready_to_run(self, organization_id: UUID, job_id: UUID) -> bool:
        """Whether every dependency of *job_id* is currently satisfied.

        A job with no dependencies at all is trivially ready -- there is
        nothing to wait for.
        """
        edges = await self._dependencies.list_parents_of(organization_id, job_id)
        if not edges:
            return True
        for edge in edges:
            latest = await self._executions.latest_for_job(organization_id, edge.parent_job_id)
            latest_status = execution_status_of(latest.status) if latest else None
            if not is_satisfied(condition=edge.condition, parent_latest_status=latest_status):
                return False
        return True


__all__ = ["DependencyService"]
