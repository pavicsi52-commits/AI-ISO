"""Validation profile lifecycle. Per docs/043 "VALIDATION PROFILES":
Infrastructure/Cloud/Kubernetes/.../Custom Profiles, Versioning.
``current_version_number`` bumps its own patch component on every
update -- the same lightweight, no-separate-version-table scheme
``services/workflow-runtime-service``'s own
``WorkflowVersionService._bump_patch`` already established, chosen
here since docs/043's own 17-table list has no
``validation_profile_versions`` table.
"""

from __future__ import annotations

from uuid import UUID

from app.models.enums import (
    ValidationConcurrencyStrategy,
    ValidationProfileType,
    ValidationTargetType,
)
from app.models.validation_profile import ValidationProfile
from app.repositories.validation_profile import ValidationProfileRepository

_INITIAL_VERSION = "1.0.0"


def _bump_patch(version_number: str) -> str:
    major, minor, patch = version_number.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


class ValidationProfileService:
    """Creates, reads, updates, and deletes validation profiles."""

    def __init__(self, profiles: ValidationProfileRepository) -> None:
        self._profiles = profiles

    async def get_by_id(self, profile_id: UUID) -> ValidationProfile:
        """Return the validation profile identified by *profile_id*.

        Raises:
            NotFoundError: If no such profile exists.
        """
        return await self._profiles.require_by_id(profile_id)

    async def list_for_org(self, organization_id: UUID) -> list[ValidationProfile]:
        """Every validation profile belonging to *organization_id*."""
        return await self._profiles.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        description: str | None,
        profile_type: ValidationProfileType,
        target_types: list[ValidationTargetType],
        check_ids: list[UUID],
        concurrency_strategy: ValidationConcurrencyStrategy,
        scoring_weights: dict[str, float],
        tags: list[str],
        owner: str | None,
    ) -> ValidationProfile:
        """Create a new validation profile ("Create")."""
        return await self._profiles.create(
            ValidationProfile(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                description=description,
                profile_type=profile_type,
                target_types=[str(t) for t in target_types],
                check_ids=[str(check_id) for check_id in check_ids],
                concurrency_strategy=concurrency_strategy,
                scoring_weights=scoring_weights,
                tags=tags,
                owner=owner,
                current_version_number=_INITIAL_VERSION,
            )
        )

    async def update(
        self,
        profile_id: UUID,
        *,
        name: str,
        description: str | None,
        target_types: list[ValidationTargetType],
        check_ids: list[UUID],
        concurrency_strategy: ValidationConcurrencyStrategy,
        scoring_weights: dict[str, float],
        tags: list[str],
        owner: str | None,
    ) -> ValidationProfile:
        """Replace a profile's own metadata and bump its own version ("Update").

        Raises:
            NotFoundError: If *profile_id* does not exist.
        """
        profile = await self.get_by_id(profile_id)
        profile.name = name
        profile.description = description
        profile.target_types = [str(t) for t in target_types]
        profile.check_ids = [str(check_id) for check_id in check_ids]
        profile.concurrency_strategy = concurrency_strategy
        profile.scoring_weights = scoring_weights
        profile.tags = tags
        profile.owner = owner
        profile.current_version_number = _bump_patch(profile.current_version_number)
        return await self._profiles.update(profile)

    async def delete(self, profile_id: UUID) -> None:
        """Soft-delete a validation profile ("Delete")."""
        await self._profiles.delete(profile_id)


__all__ = ["ValidationProfileService"]
