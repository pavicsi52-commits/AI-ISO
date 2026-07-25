"""Ansible inventory bundles.

Per docs/039 "ANSIBLE INTEGRATION" "Support". Every create is validated
against Ansible's own dynamic-inventory shape via
:func:`app.ansible.validator.validate_ansible_inventory_or_raise`
before persistence.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.ansible.validator import AnsibleValidationError, validate_ansible_inventory_or_raise
from app.models.configuration_ansible_inventory import ConfigurationAnsibleInventory
from app.repositories.configuration_ansible_inventory import (
    ConfigurationAnsibleInventoryRepository,
)


class ConfigurationAnsibleService:
    """Creates, reads, and lists Ansible inventory bundles."""

    def __init__(self, inventories: ConfigurationAnsibleInventoryRepository) -> None:
        self._inventories = inventories

    async def get_by_id(self, inventory_id: UUID) -> ConfigurationAnsibleInventory:
        """Return the Ansible inventory bundle identified by *inventory_id*.

        Raises:
            NotFoundError: If no such inventory bundle exists.
        """
        return await self._inventories.require_by_id(inventory_id)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationAnsibleInventory]:
        """Every Ansible inventory bundle backing *profile_id*."""
        return await self._inventories.list_for_profile(profile_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        profile_id: UUID | None,
        name: str,
        inventory_content: dict[str, Any],
        host_vars: dict[str, Any],
        group_vars: dict[str, Any],
        playbooks: list[str],
        roles: list[str],
        collections: list[str],
        vault_ref: str | None,
    ) -> ConfigurationAnsibleInventory:
        """Define a new Ansible inventory bundle.

        Raises:
            ValidationError: If the inventory bundle's structure is invalid.
        """
        try:
            validate_ansible_inventory_or_raise(
                inventory_content, host_vars=host_vars, group_vars=group_vars, playbooks=playbooks
            )
        except AnsibleValidationError as exc:
            raise ValidationError(str(exc)) from exc
        return await self._inventories.create(
            ConfigurationAnsibleInventory(
                organization_id=organization_id,
                project_id=project_id,
                profile_id=profile_id,
                name=name,
                inventory_content=inventory_content,
                host_vars=host_vars,
                group_vars=group_vars,
                playbooks=playbooks,
                roles=roles,
                collections=collections,
                vault_ref=vault_ref,
            )
        )

    async def delete(self, inventory_id: UUID) -> None:
        """Soft-delete an Ansible inventory bundle."""
        await self._inventories.delete(inventory_id)


__all__ = ["ConfigurationAnsibleService"]
