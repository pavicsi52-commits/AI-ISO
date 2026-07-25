"""Scoped configuration variables.

Per docs/039 "CONFIGURATION VARIABLES" "Support": Global, Organization,
Project, Environment, Asset, Secrets References, Runtime, Computed
Variables, Validation Rules.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError

from app.models.configuration_variable import ConfigurationVariable
from app.models.enums import VariableScope
from app.repositories.configuration_variable import ConfigurationVariableRepository


class ConfigurationVariableService:
    """Creates, reads, updates, and deletes scoped configuration variables."""

    def __init__(self, variables: ConfigurationVariableRepository) -> None:
        self._variables = variables

    async def get_by_id(self, variable_id: UUID) -> ConfigurationVariable:
        """Return the variable identified by *variable_id*.

        Raises:
            NotFoundError: If no such variable exists.
        """
        return await self._variables.require_by_id(variable_id)

    async def list_for_scope(
        self, organization_id: UUID, scope: VariableScope, *, scope_ref_id: UUID | None = None
    ) -> list[ConfigurationVariable]:
        """Every variable at *scope* for *organization_id*."""
        return await self._variables.list_for_scope(
            organization_id, scope, scope_ref_id=scope_ref_id
        )

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        scope: VariableScope,
        scope_ref_id: UUID | None,
        key: str,
        value: str | None,
        is_secret_reference: bool,
        is_computed: bool,
        validation_rule: dict[str, Any] | None,
    ) -> ConfigurationVariable:
        """Define a new scoped variable.

        Raises:
            ConflictError: If *key* is already defined at this exact scope.
            ValidationError: If both ``is_secret_reference`` and
                ``is_computed`` are set (a variable cannot be both a
                secret reference and a computed value).
        """
        if is_secret_reference and is_computed:
            raise ValidationError(
                "A configuration variable cannot be both a secret reference and computed."
            )
        existing = await self._variables.get_by_key(organization_id, scope, scope_ref_id, key)
        if existing is not None:
            raise ConflictError(f"Variable {key!r} is already defined at this scope.")
        return await self._variables.create(
            ConfigurationVariable(
                organization_id=organization_id,
                project_id=project_id,
                scope=scope,
                scope_ref_id=scope_ref_id,
                key=key,
                value=value,
                is_secret_reference=is_secret_reference,
                is_computed=is_computed,
                validation_rule=validation_rule,
            )
        )

    async def update(
        self,
        variable_id: UUID,
        *,
        value: str | None,
        is_secret_reference: bool,
        is_computed: bool,
        validation_rule: dict[str, Any] | None,
    ) -> ConfigurationVariable:
        """Replace a variable's value/flags/validation rule."""
        if is_secret_reference and is_computed:
            raise ValidationError(
                "A configuration variable cannot be both a secret reference and computed."
            )
        variable = await self.get_by_id(variable_id)
        variable.value = value
        variable.is_secret_reference = is_secret_reference
        variable.is_computed = is_computed
        variable.validation_rule = validation_rule
        return await self._variables.update(variable)

    async def delete(self, variable_id: UUID) -> None:
        """Soft-delete a variable."""
        await self._variables.delete(variable_id)


__all__ = ["ConfigurationVariableService"]
