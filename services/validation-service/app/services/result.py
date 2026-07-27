"""Read access to validation results and their own raw collected-data details."""

from __future__ import annotations

from uuid import UUID

from app.models.validation_result import ValidationResult
from app.models.validation_result_detail import ValidationResultDetail
from app.repositories.validation_result import ValidationResultRepository
from app.repositories.validation_result_detail import ValidationResultDetailRepository


class ValidationResultService:
    """Reads validation results and their own detail rows."""

    def __init__(
        self, results: ValidationResultRepository, details: ValidationResultDetailRepository
    ) -> None:
        self._results = results
        self._details = details

    async def get_by_id(self, result_id: UUID) -> ValidationResult:
        """Return the result identified by *result_id*.

        Raises:
            NotFoundError: If no such result exists.
        """
        return await self._results.require_by_id(result_id)

    async def list_for_execution(self, execution_id: UUID) -> list[ValidationResult]:
        """Every result recorded for *execution_id*."""
        return await self._results.list_for_execution(execution_id)

    async def list_for_target(self, target_id: UUID) -> list[ValidationResult]:
        """Every result ever recorded for *target_id*, across every execution."""
        return await self._results.list_for_target(target_id)

    async def list_details(self, result_id: UUID) -> list[ValidationResultDetail]:
        """Every raw collected data point backing *result_id*."""
        return await self._details.list_for_result(result_id)


__all__ = ["ValidationResultService"]
