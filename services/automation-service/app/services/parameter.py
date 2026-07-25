"""Job input-parameter definitions."""

from __future__ import annotations

from uuid import UUID

from app.models.automation_parameter import AutomationParameter
from app.repositories.automation_job import AutomationJobRepository
from app.repositories.automation_parameter import AutomationParameterRepository


class AutomationParameterService:
    """Creates, reads, and deletes automation job input-parameter definitions."""

    def __init__(
        self, parameters: AutomationParameterRepository, jobs: AutomationJobRepository
    ) -> None:
        self._parameters = parameters
        self._jobs = jobs

    async def list_for_job(self, job_id: UUID) -> list[AutomationParameter]:
        """Every parameter definition for *job_id*."""
        return await self._parameters.list_for_job(job_id)

    async def create(
        self,
        job_id: UUID,
        *,
        name: str,
        parameter_type: str,
        required: bool,
        default_value: str | None,
        description: str | None,
    ) -> AutomationParameter:
        """Define a new input-parameter for a job.

        Raises:
            NotFoundError: If *job_id* does not exist.
        """
        job = await self._jobs.require_by_id(job_id)
        return await self._parameters.create(
            AutomationParameter(
                organization_id=job.organization_id,
                job_id=job_id,
                name=name,
                parameter_type=parameter_type,
                required=required,
                default_value=default_value,
                description=description,
            )
        )

    async def delete(self, parameter_id: UUID) -> None:
        """Soft-delete a parameter definition."""
        await self._parameters.delete(parameter_id)


__all__ = ["AutomationParameterService"]
