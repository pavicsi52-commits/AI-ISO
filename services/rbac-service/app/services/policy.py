"""Authorization policy management.

Per docs/032 "POLICY ENGINE" and REST list: ``POST/GET/PUT/DELETE
/policies``. A policy's conditions and its initial subject assignment
are created/replaced together with the policy itself -- see
``app/schemas/policy.py``'s docstring for why.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.constants import DEFAULT_ORGANIZATION_ID
from app.events.rbac_events import PolicyCreatedEvent, PolicyDeletedEvent, PolicyUpdatedEvent
from app.models.authorization_policy import AuthorizationPolicy
from app.models.enums import (
    PermissionAction,
    PolicyConditionType,
    PolicyEffect,
    PolicyStatus,
    ResourceType,
    SubjectType,
)
from app.models.policy_assignment import PolicyAssignment
from app.models.policy_condition import PolicyCondition
from app.repositories.authorization_policy import AuthorizationPolicyRepository
from app.repositories.policy_assignment import PolicyAssignmentRepository
from app.repositories.policy_condition import PolicyConditionRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ConditionInput:
    """One condition to attach when creating/updating a policy."""

    condition_type: PolicyConditionType
    field: str | None
    operator: str
    value: Any


@dataclass(frozen=True, slots=True)
class PolicyWithConditions:
    """A policy alongside the conditions currently attached to it."""

    policy: AuthorizationPolicy
    conditions: list[PolicyCondition]


class PolicyService:
    """Creates, updates, deletes, and lists authorization policies."""

    def __init__(
        self,
        policies: AuthorizationPolicyRepository,
        conditions: PolicyConditionRepository,
        assignments: PolicyAssignmentRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._policies = policies
        self._conditions = conditions
        self._assignments = assignments
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, policy_id: UUID) -> PolicyWithConditions:
        """Return the policy identified by *policy_id*, with its conditions.

        Raises:
            NotFoundError: If no such policy exists.
        """
        policy = await self._policies.require_by_id(policy_id)
        conditions = await self._conditions.list_for_policy(policy_id)
        return PolicyWithConditions(policy=policy, conditions=conditions)

    async def list_active(self) -> list[PolicyWithConditions]:
        """Every active policy, with its conditions, highest priority first."""
        policies = await self._policies.list_active()
        return [
            PolicyWithConditions(
                policy=policy, conditions=await self._conditions.list_for_policy(policy.id)
            )
            for policy in policies
        ]

    async def create(
        self,
        *,
        name: str,
        code: str,
        description: str | None,
        effect: PolicyEffect,
        resource_type: ResourceType | None,
        action: PermissionAction | None,
        priority: int,
        conditions: list[ConditionInput],
        subject_type: SubjectType,
        subject_id: UUID | None,
        metadata: dict[str, Any],
    ) -> PolicyWithConditions:
        """Create a new policy, its conditions, and its initial assignment ("Allow"/"Deny")."""
        policy = await self._policies.create(
            AuthorizationPolicy(
                name=name,
                code=code,
                description=description,
                effect=effect,
                resource_type=resource_type,
                action=action,
                priority=priority,
                metadata_=metadata,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        created_conditions = await self._create_conditions(policy.id, conditions)
        await self._assignments.create(
            PolicyAssignment(
                policy_id=policy.id,
                subject_type=subject_type,
                subject_id=subject_id,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        await self._publish(
            PolicyCreatedEvent(source_service="rbac-service", payload={"policy_id": str(policy.id)})
        )
        return PolicyWithConditions(policy=policy, conditions=created_conditions)

    async def update(
        self,
        policy_id: UUID,
        *,
        name: str,
        description: str | None,
        effect: PolicyEffect,
        resource_type: ResourceType | None,
        action: PermissionAction | None,
        priority: int,
        status: PolicyStatus,
        conditions: list[ConditionInput],
        metadata: dict[str, Any],
    ) -> PolicyWithConditions:
        """Update a policy's fields and replace its condition set."""
        policy = await self._policies.require_by_id(policy_id)
        policy.name = name
        policy.description = description
        policy.effect = effect
        policy.resource_type = resource_type
        policy.action = action
        policy.priority = priority
        policy.status = status
        policy.metadata_ = metadata

        for existing in await self._conditions.list_for_policy(policy_id):
            await self._conditions.delete(existing.id)
        created_conditions = await self._create_conditions(policy_id, conditions)

        await self._publish(
            PolicyUpdatedEvent(source_service="rbac-service", payload={"policy_id": str(policy.id)})
        )
        return PolicyWithConditions(policy=policy, conditions=created_conditions)

    async def delete(self, policy_id: UUID) -> None:
        """Soft-delete a policy."""
        await self._policies.require_by_id(policy_id)
        await self._policies.delete(policy_id)
        await self._publish(
            PolicyDeletedEvent(source_service="rbac-service", payload={"policy_id": str(policy_id)})
        )

    async def _create_conditions(
        self, policy_id: UUID, conditions: list[ConditionInput]
    ) -> list[PolicyCondition]:
        created = []
        for condition in conditions:
            created.append(
                await self._conditions.create(
                    PolicyCondition(
                        policy_id=policy_id,
                        condition_type=condition.condition_type,
                        field=condition.field,
                        operator=condition.operator,
                        value=condition.value,
                        organization_id=DEFAULT_ORGANIZATION_ID,
                    )
                )
            )
        return created


__all__ = ["ConditionInput", "PolicyService", "PolicyWithConditions"]
