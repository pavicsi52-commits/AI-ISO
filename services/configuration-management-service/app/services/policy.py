"""Governance policies enforced against configuration profiles.

Per docs/039 "POLICIES" "Support": Naming, Version, Approval,
Compliance, Deployment, Retention, Environment Policies. Uniqueness of
``(organization_id, name)`` is enforced by the table's own constraint
(``uq_configuration_policy_name``) -- a duplicate name surfaces as
:class:`~shared_core.exceptions.database.DuplicateRecordError` from
:meth:`~shared_core.database.repository.BaseRepository.create` itself,
the same "let the database enforce it, don't duplicate the check"
convention every prior AI-IOS service already follows for
constraint-backed uniqueness.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.configuration_policy import ConfigurationPolicy
from app.models.enums import PolicyType
from app.repositories.configuration_policy import ConfigurationPolicyRepository


class ConfigurationPolicyService:
    """Creates, reads, updates, and deletes configuration governance policies."""

    def __init__(self, policies: ConfigurationPolicyRepository) -> None:
        self._policies = policies

    async def get_by_id(self, policy_id: UUID) -> ConfigurationPolicy:
        """Return the policy identified by *policy_id*.

        Raises:
            NotFoundError: If no such policy exists.
        """
        return await self._policies.require_by_id(policy_id)

    async def list_for_org(
        self, organization_id: UUID, *, policy_type: PolicyType | None = None
    ) -> list[ConfigurationPolicy]:
        """Every policy belonging to *organization_id*."""
        return await self._policies.list_for_org(organization_id, policy_type=policy_type)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        policy_type: PolicyType,
        name: str,
        description: str | None,
        rule: dict[str, Any],
        enforced: bool,
    ) -> ConfigurationPolicy:
        """Define a new governance policy.

        Raises:
            DuplicateRecordError: If *name* is already registered for the organization.
        """
        return await self._policies.create(
            ConfigurationPolicy(
                organization_id=organization_id,
                project_id=project_id,
                policy_type=policy_type,
                name=name,
                description=description,
                rule=rule,
                enforced=enforced,
            )
        )

    async def update(
        self,
        policy_id: UUID,
        *,
        description: str | None,
        rule: dict[str, Any],
        enforced: bool,
    ) -> ConfigurationPolicy:
        """Replace a policy's rule/description/enforcement flag."""
        policy = await self.get_by_id(policy_id)
        policy.description = description
        policy.rule = rule
        policy.enforced = enforced
        return await self._policies.update(policy)

    async def delete(self, policy_id: UUID) -> None:
        """Soft-delete a governance policy."""
        await self._policies.delete(policy_id)


__all__ = ["ConfigurationPolicyService"]
