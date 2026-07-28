"""Target dependency graph CRUD and blast-radius resolution
("DEPENDENCY HEALTH" "Support": Topology-aware Health, Parent/Child
Health, Blast Radius Calculation).
"""

from __future__ import annotations

from uuid import UUID

from app.models.enums import DependencyType
from app.models.monitoring_dependency import MonitoringDependency
from app.repositories.monitoring_dependency import MonitoringDependencyRepository


class MonitoringDependencyService:
    """Creates and reads dependency graph edges."""

    def __init__(self, dependencies: MonitoringDependencyRepository) -> None:
        self._dependencies = dependencies

    async def list_children(self, parent_target_id: UUID) -> list[MonitoringDependency]:
        """Every target that depends on *parent_target_id* ("Blast Radius Calculation")."""
        return await self._dependencies.list_children(parent_target_id)

    async def list_parents(self, child_target_id: UUID) -> list[MonitoringDependency]:
        """Every target *child_target_id* itself depends on."""
        return await self._dependencies.list_parents(child_target_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        parent_target_id: UUID,
        child_target_id: UUID,
        dependency_type: DependencyType,
    ) -> MonitoringDependency:
        """Register a new dependency edge."""
        return await self._dependencies.create(
            MonitoringDependency(
                organization_id=organization_id,
                parent_target_id=parent_target_id,
                child_target_id=child_target_id,
                dependency_type=dependency_type,
            )
        )


__all__ = ["MonitoringDependencyService"]
