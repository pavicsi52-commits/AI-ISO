"""Discovery filter management. No REST surface of its own -- see
``app/services/rule.py``'s identical rationale.

**Not yet applied by the execution engine**: unlike
``DiscoveryRuleService``'s ``INCLUDE``/``EXCLUDE``/``CLASSIFICATION``
rule types (see ``app/services/discovery_execution.py``'s own module
docstring for exactly which rule types that engine reads), docs/037
gives "Filters" no application semantics beyond a one-line "Support"
mention -- there's no specified relationship between a named
:class:`DiscoveryFilter` and a job/profile/target to actually evaluate
one against. CRUD is real and complete; wiring it into the execution
engine is left for whenever that relationship is specified, the same
"stored, not silently faked" honesty this package applies to every
other documented-but-underspecified gap.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.discovery_filter import DiscoveryFilter
from app.models.enums import FilterAppliesTo
from app.repositories.discovery_filter import DiscoveryFilterRepository


class DiscoveryFilterService:
    """Creates and lists named, reusable filter criteria sets."""

    def __init__(self, filters: DiscoveryFilterRepository) -> None:
        self._filters = filters

    async def list_for_org(self, organization_id: UUID) -> list[DiscoveryFilter]:
        """Every active filter defined for *organization_id*."""
        return await self._filters.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        name: str,
        applies_to: FilterAppliesTo,
        filter_criteria: dict[str, Any],
    ) -> DiscoveryFilter:
        """Create a new filter."""
        return await self._filters.create(
            DiscoveryFilter(
                organization_id=organization_id,
                name=name,
                applies_to=applies_to,
                filter_criteria=filter_criteria,
            )
        )

    async def delete(self, filter_id: UUID) -> None:
        """Delete a filter.

        Raises:
            NotFoundError: If no such filter exists.
        """
        await self._filters.delete(filter_id)


__all__ = ["DiscoveryFilterService"]
