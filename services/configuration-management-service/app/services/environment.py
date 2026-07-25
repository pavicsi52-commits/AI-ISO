"""Environment definitions an organization tracks profiles against.

Per docs/039 "ENVIRONMENTS" "Support": Development, Testing, QA,
Staging, Production, Disaster Recovery, Edge, Industrial, Custom.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.configuration_environment import ConfigurationEnvironment
from app.models.enums import EnvironmentType
from app.repositories.configuration_environment import ConfigurationEnvironmentRepository


class ConfigurationEnvironmentService:
    """Creates, reads, updates, and deletes environment definitions."""

    def __init__(self, environments: ConfigurationEnvironmentRepository) -> None:
        self._environments = environments

    async def get_by_id(self, environment_id: UUID) -> ConfigurationEnvironment:
        """Return the environment identified by *environment_id*.

        Raises:
            NotFoundError: If no such environment exists.
        """
        return await self._environments.require_by_id(environment_id)

    async def list_for_org(self, organization_id: UUID) -> list[ConfigurationEnvironment]:
        """Every environment definition for *organization_id*."""
        return await self._environments.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        environment_type: EnvironmentType,
        description: str | None,
    ) -> ConfigurationEnvironment:
        """Define a new environment.

        Raises:
            ConflictError: If *name* is already registered for the organization.
        """
        if await self._environments.get_by_name(organization_id, name) is not None:
            raise ConflictError(f"Environment {name!r} is already registered.")
        return await self._environments.create(
            ConfigurationEnvironment(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                environment_type=environment_type,
                description=description,
            )
        )

    async def update(
        self,
        environment_id: UUID,
        *,
        environment_type: EnvironmentType,
        description: str | None,
    ) -> ConfigurationEnvironment:
        """Replace an environment's type/description."""
        environment = await self.get_by_id(environment_id)
        environment.environment_type = environment_type
        environment.description = description
        return await self._environments.update(environment)

    async def delete(self, environment_id: UUID) -> None:
        """Soft-delete an environment definition."""
        await self._environments.delete(environment_id)


__all__ = ["ConfigurationEnvironmentService"]
