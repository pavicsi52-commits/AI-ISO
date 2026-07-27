"""Validation failure lifecycle -- durable, resolvable records of a failed result."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.enums import ValidationSeverity
from app.models.validation_failure import ValidationFailure
from app.repositories.validation_failure import ValidationFailureRepository


class ValidationFailureService:
    """Creates, reads, and resolves validation failures."""

    def __init__(self, failures: ValidationFailureRepository) -> None:
        self._failures = failures

    async def get_by_id(self, failure_id: UUID) -> ValidationFailure:
        """Return the failure identified by *failure_id*.

        Raises:
            NotFoundError: If no such failure exists.
        """
        return await self._failures.require_by_id(failure_id)

    async def list_for_result(self, result_id: UUID) -> list[ValidationFailure]:
        """Every failure recorded for *result_id*."""
        return await self._failures.list_for_result(result_id)

    async def list_unresolved_for_org(self, organization_id: UUID) -> list[ValidationFailure]:
        """Every unresolved failure for *organization_id*."""
        return await self._failures.list_unresolved_for_org(organization_id)

    async def record(
        self, *, organization_id: UUID, result_id: UUID, severity: ValidationSeverity, reason: str
    ) -> ValidationFailure:
        """Record a new validation failure."""
        return await self._failures.create(
            ValidationFailure(
                organization_id=organization_id,
                result_id=result_id,
                severity=severity,
                reason=reason,
            )
        )

    async def resolve(self, failure_id: UUID, *, resolved_by: UUID) -> ValidationFailure:
        """Mark a failure as resolved.

        Raises:
            NotFoundError: If *failure_id* does not exist.
        """
        failure = await self.get_by_id(failure_id)
        failure.is_resolved = True
        failure.resolved_at = datetime.now(UTC)
        failure.resolved_by = resolved_by
        return await self._failures.update(failure)


__all__ = ["ValidationFailureService"]
