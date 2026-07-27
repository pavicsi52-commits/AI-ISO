"""Remediation suggestion CRUD. Per docs/043 "REMEDIATION" "Support":
Recommended Fixes, Automation Integration, Knowledge Base Links,
Playbook Suggestions, Workflow Suggestions, Manual Actions, AI
Recommendation Hooks.

Applying a suggested fix is never done automatically by this service --
:meth:`mark_applied` only ever records a caller's own explicit
confirmation that they ran the automation job/playbook/workflow
elsewhere; this service has no mechanism to genuinely trigger and
verify a remediation's own real-world effect.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.enums import RemediationActionType
from app.models.validation_remediation import ValidationRemediation
from app.repositories.validation_remediation import ValidationRemediationRepository


class ValidationRemediationService:
    """Creates, reads, and records the application of remediation suggestions."""

    def __init__(self, remediations: ValidationRemediationRepository) -> None:
        self._remediations = remediations

    async def get_by_id(self, remediation_id: UUID) -> ValidationRemediation:
        """Return the remediation identified by *remediation_id*.

        Raises:
            NotFoundError: If no such remediation exists.
        """
        return await self._remediations.require_by_id(remediation_id)

    async def list_for_failure(self, failure_id: UUID) -> list[ValidationRemediation]:
        """Every remediation suggested for *failure_id*."""
        return await self._remediations.list_for_failure(failure_id)

    async def list_for_org(self, organization_id: UUID) -> list[ValidationRemediation]:
        """Every remediation ever suggested for *organization_id* ("Generate")."""
        return await self._remediations.list_for_org(organization_id)

    async def suggest(
        self,
        *,
        organization_id: UUID,
        failure_id: UUID,
        action_type: RemediationActionType,
        description: str,
        automation_job_key: str | None = None,
        playbook_key: str | None = None,
        workflow_key: str | None = None,
        knowledge_base_url: str | None = None,
    ) -> ValidationRemediation:
        """Record a new remediation suggestion for a known failure."""
        return await self._remediations.create(
            ValidationRemediation(
                organization_id=organization_id,
                failure_id=failure_id,
                action_type=action_type,
                description=description,
                automation_job_key=automation_job_key,
                playbook_key=playbook_key,
                workflow_key=workflow_key,
                knowledge_base_url=knowledge_base_url,
            )
        )

    async def mark_applied(
        self, remediation_id: UUID, *, applied_by: UUID
    ) -> ValidationRemediation:
        """Record that a caller has applied a suggested remediation elsewhere.

        Raises:
            NotFoundError: If *remediation_id* does not exist.
        """
        remediation = await self.get_by_id(remediation_id)
        remediation.is_applied = True
        remediation.applied_at = datetime.now(UTC)
        remediation.applied_by = applied_by
        return await self._remediations.update(remediation)


__all__ = ["ValidationRemediationService"]
