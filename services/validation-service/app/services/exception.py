"""Validation exception (waiver) approval workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.enums import ValidationExceptionStatus
from app.models.validation_exception import ValidationException
from app.repositories.validation_exception import ValidationExceptionRepository


class ValidationExceptionService:
    """Requests, decides, and lists validation exceptions."""

    def __init__(self, exceptions: ValidationExceptionRepository) -> None:
        self._exceptions = exceptions

    async def get_by_id(self, exception_id: UUID) -> ValidationException:
        """Return the exception identified by *exception_id*.

        Raises:
            NotFoundError: If no such exception exists.
        """
        return await self._exceptions.require_by_id(exception_id)

    async def list_for_failure(self, failure_id: UUID) -> list[ValidationException]:
        """Every exception ever requested for *failure_id*."""
        return await self._exceptions.list_for_failure(failure_id)

    async def list_pending_for_org(self, organization_id: UUID) -> list[ValidationException]:
        """Every exception request for *organization_id* still awaiting a decision."""
        return await self._exceptions.list_pending_for_org(organization_id)

    async def request(
        self,
        *,
        organization_id: UUID,
        failure_id: UUID,
        reason: str,
        requested_by: UUID,
        expires_at: datetime | None,
    ) -> ValidationException:
        """Request a waiver for a known failure ("Validation Exceptions")."""
        return await self._exceptions.create(
            ValidationException(
                organization_id=organization_id,
                failure_id=failure_id,
                reason=reason,
                requested_by=requested_by,
                expires_at=expires_at,
            )
        )

    async def decide(
        self,
        exception_id: UUID,
        *,
        approve: bool,
        decided_by: UUID,
        decision_reason: str | None,
    ) -> ValidationException:
        """Approve or reject a pending exception request.

        Raises:
            NotFoundError: If *exception_id* does not exist.
            ConflictError: If it has already been decided.
        """
        exception = await self.get_by_id(exception_id)
        if exception.status != ValidationExceptionStatus.PENDING:
            raise ConflictError(
                f"Validation exception {exception_id!r} has already been "
                f"{str(exception.status)!r}."
            )
        exception.status = (
            ValidationExceptionStatus.APPROVED if approve else ValidationExceptionStatus.REJECTED
        )
        exception.decided_by = decided_by
        exception.decided_at = datetime.now(UTC)
        exception.decision_reason = decision_reason
        return await self._exceptions.update(exception)


__all__ = ["ValidationExceptionService"]
