"""Golden/compliance/security/performance/vendor/custom baselines.

Per docs/039 "BASELINES" "Support".
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.configuration_baseline import ConfigurationBaseline
from app.models.enums import BaselineType
from app.repositories.configuration_baseline import ConfigurationBaselineRepository


class ConfigurationBaselineService:
    """Creates, reads, updates, and deletes configuration baselines."""

    def __init__(self, baselines: ConfigurationBaselineRepository) -> None:
        self._baselines = baselines

    async def get_by_id(self, baseline_id: UUID) -> ConfigurationBaseline:
        """Return the baseline identified by *baseline_id*.

        Raises:
            NotFoundError: If no such baseline exists.
        """
        return await self._baselines.require_by_id(baseline_id)

    async def list_for_org(
        self, organization_id: UUID, *, baseline_type: BaselineType | None = None
    ) -> list[ConfigurationBaseline]:
        """Every baseline belonging to *organization_id*."""
        return await self._baselines.list_for_org(organization_id, baseline_type=baseline_type)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationBaseline]:
        """Every baseline associated with *profile_id*."""
        return await self._baselines.list_for_profile(profile_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        profile_id: UUID | None,
        baseline_type: BaselineType,
        name: str,
        description: str | None,
        content: dict[str, Any],
    ) -> ConfigurationBaseline:
        """Define a new baseline."""
        return await self._baselines.create(
            ConfigurationBaseline(
                organization_id=organization_id,
                project_id=project_id,
                profile_id=profile_id,
                baseline_type=baseline_type,
                name=name,
                description=description,
                content=content,
            )
        )

    async def update(
        self,
        baseline_id: UUID,
        *,
        name: str,
        description: str | None,
        content: dict[str, Any],
    ) -> ConfigurationBaseline:
        """Replace a baseline's fields ("Version History" tracked via profile versioning)."""
        baseline = await self.get_by_id(baseline_id)
        baseline.name = name
        baseline.description = description
        baseline.content = content
        return await self._baselines.update(baseline)

    async def delete(self, baseline_id: UUID) -> None:
        """Soft-delete a baseline."""
        await self._baselines.delete(baseline_id)


__all__ = ["ConfigurationBaselineService"]
