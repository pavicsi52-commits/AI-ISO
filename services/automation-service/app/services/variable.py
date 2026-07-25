"""Scoped automation variables. Per docs/040 "WORKFLOW INTEGRATION" "Shared Variables"."""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.automation_variable import AutomationVariable
from app.models.enums import VariableScope
from app.repositories.automation_variable import AutomationVariableRepository


class AutomationVariableService:
    """Creates, reads, updates, and deletes scoped automation variables."""

    def __init__(self, variables: AutomationVariableRepository) -> None:
        self._variables = variables

    async def get_by_id(self, variable_id: UUID) -> AutomationVariable:
        """Return the variable identified by *variable_id*.

        Raises:
            NotFoundError: If no such variable exists.
        """
        return await self._variables.require_by_id(variable_id)

    async def list_for_scope(
        self, organization_id: UUID, scope: VariableScope, *, scope_ref_id: UUID | None = None
    ) -> list[AutomationVariable]:
        """Every variable at *scope* for *organization_id*."""
        return await self._variables.list_for_scope(
            organization_id, scope, scope_ref_id=scope_ref_id
        )

    async def create(
        self,
        *,
        organization_id: UUID,
        scope: VariableScope,
        scope_ref_id: UUID | None,
        key: str,
        value: str | None,
        is_secret_reference: bool,
    ) -> AutomationVariable:
        """Define a new scoped variable.

        Raises:
            ConflictError: If *key* is already defined at this exact scope.
        """
        existing = await self._variables.get_by_key(organization_id, scope, scope_ref_id, key)
        if existing is not None:
            raise ConflictError(f"Variable {key!r} is already defined at this scope.")
        return await self._variables.create(
            AutomationVariable(
                organization_id=organization_id,
                scope=scope,
                scope_ref_id=scope_ref_id,
                key=key,
                value=value,
                is_secret_reference=is_secret_reference,
            )
        )

    async def update(
        self, variable_id: UUID, *, value: str | None, is_secret_reference: bool
    ) -> AutomationVariable:
        """Replace a variable's value/secret-reference flag."""
        variable = await self.get_by_id(variable_id)
        variable.value = value
        variable.is_secret_reference = is_secret_reference
        return await self._variables.update(variable)

    async def delete(self, variable_id: UUID) -> None:
        """Soft-delete a variable."""
        await self._variables.delete(variable_id)


__all__ = ["AutomationVariableService"]
