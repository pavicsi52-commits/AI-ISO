"""Scheduled synthetic check configuration CRUD ("SYNTHETIC MONITORING"
"Support").
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import SyntheticCheckType
from app.models.monitoring_synthetic_test import MonitoringSyntheticTest
from app.repositories.monitoring_synthetic_test import MonitoringSyntheticTestRepository


class MonitoringSyntheticTestService:
    """Creates and reads scheduled synthetic check configurations."""

    def __init__(self, tests: MonitoringSyntheticTestRepository) -> None:
        self._tests = tests

    async def get_by_id(self, test_id: UUID) -> MonitoringSyntheticTest:
        """Return the synthetic test identified by *test_id*.

        Raises:
            NotFoundError: If no such synthetic test exists.
        """
        return await self._tests.require_by_id(test_id)

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringSyntheticTest]:
        """Every synthetic test belonging to *organization_id*."""
        return await self._tests.list_for_org(organization_id)

    async def list_all_active(self) -> list[MonitoringSyntheticTest]:
        """Every active synthetic test, system-wide ("Scheduled Tests")."""
        return await self._tests.list_all_active()

    async def create(
        self,
        *,
        organization_id: UUID,
        target_id: UUID | None,
        check_type: SyntheticCheckType,
        name: str,
        parameters: dict[str, Any],
        interval_seconds: float,
        is_active: bool,
    ) -> MonitoringSyntheticTest:
        """Register a new scheduled synthetic check."""
        return await self._tests.create(
            MonitoringSyntheticTest(
                organization_id=organization_id,
                target_id=target_id,
                check_type=check_type,
                name=name,
                parameters=parameters,
                interval_seconds=interval_seconds,
                is_active=is_active,
            )
        )


__all__ = ["MonitoringSyntheticTestService"]
