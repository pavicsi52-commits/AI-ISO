"""Reusable validation check catalog CRUD ("Reusable Check Libraries")."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import ValidationCheckType
from app.models.validation_check import ValidationCheck
from app.repositories.validation_check import ValidationCheckRepository


class ValidationCheckService:
    """Creates and reads reusable validation checks."""

    def __init__(self, checks: ValidationCheckRepository) -> None:
        self._checks = checks

    async def get_by_id(self, check_id: UUID) -> ValidationCheck:
        """Return the check identified by *check_id*.

        Raises:
            NotFoundError: If no such check exists.
        """
        return await self._checks.require_by_id(check_id)

    async def list_for_org(self, organization_id: UUID) -> list[ValidationCheck]:
        """Every reusable check defined for *organization_id*."""
        return await self._checks.list_for_org(organization_id)

    async def list_by_ids(self, check_ids: list[UUID]) -> list[ValidationCheck]:
        """Resolve a profile's own ``check_ids`` into their actual rows."""
        return await self._checks.list_by_ids(check_ids)

    async def create(
        self,
        *,
        organization_id: UUID,
        category_id: UUID | None,
        check_type: ValidationCheckType,
        name: str,
        description: str | None,
        collector_key: str,
        parameters: dict[str, Any],
        timeout_seconds: float,
        retry_count: int,
    ) -> ValidationCheck:
        """Create a new reusable validation check."""
        return await self._checks.create(
            ValidationCheck(
                organization_id=organization_id,
                category_id=category_id,
                check_type=check_type,
                name=name,
                description=description,
                collector_key=collector_key,
                parameters=parameters,
                timeout_seconds=timeout_seconds,
                retry_count=retry_count,
            )
        )


__all__ = ["ValidationCheckService"]
