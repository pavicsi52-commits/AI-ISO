"""Prompt template management ("PROMPT MANAGEMENT").

A prompt is an identity; its text lives in immutable versions. That
split is what makes the doc's own required capabilities real rather
than nominal:

- **Versioning** -- each revision is its own row.
- **Approval** -- only an ``APPROVED`` revision may be rendered.
- **Rollback** -- point the parent at an earlier version; nothing is
  edited in place, so the approved text stays exactly as approved.
- **Variables** -- declared per version and validated at render time.

Rendering uses Jinja2's ``SandboxedEnvironment`` via
``shared_core.workflow.expressions``' own vetted environment rather
than ``str.format`` or a raw ``Template``: a prompt template is
user-authored content, and unrestricted rendering over it would be a
real injection path into whatever the template can reach.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.ai_prompt import AiPrompt
from app.models.ai_prompt_version import AiPromptVersion
from app.models.enums import PromptStatus
from app.repositories.ai_prompt import AiPromptRepository
from app.repositories.ai_prompt_version import AiPromptVersionRepository

_environment = SandboxedEnvironment(undefined=StrictUndefined)
"""``StrictUndefined`` so a missing variable raises instead of quietly
rendering an empty string -- a prompt silently losing half its
instructions is far worse than a loud failure.
"""

_SEMVER_PARTS = 3
"""``major.minor.patch`` -- anything else is treated as unparseable."""


def bump_patch(version_number: str) -> str:
    """Return the next patch version after *version_number*.

    Falls back to appending rather than raising on a malformed input:
    a hand-edited version string should not make a prompt permanently
    un-versionable.
    """
    parts = version_number.split(".")
    if len(parts) != _SEMVER_PARTS or not all(part.isdigit() for part in parts):
        return f"{version_number}.1"
    major, minor, patch = (int(part) for part in parts)
    return f"{major}.{minor}.{patch + 1}"


class PromptService:
    """Creates, versions, approves, and renders prompt templates."""

    def __init__(self, prompts: AiPromptRepository, versions: AiPromptVersionRepository) -> None:
        self._prompts = prompts
        self._versions = versions

    async def get_by_id(self, prompt_id: UUID) -> AiPrompt:
        """Return one prompt.

        Raises:
            NotFoundError: If no such prompt exists.
        """
        return await self._prompts.require_by_id(prompt_id)

    async def list_for_org(self, organization_id: UUID) -> list[AiPrompt]:
        """Every prompt belonging to *organization_id*."""
        return await self._prompts.list_for_org(organization_id)

    async def list_versions(self, prompt_id: UUID) -> list[AiPromptVersion]:
        """Every revision of a prompt."""
        return await self._versions.list_for_prompt(prompt_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        description: str | None,
        template: str,
        variables: list[str],
    ) -> tuple[AiPrompt, AiPromptVersion]:
        """Create a prompt with its own first (draft) version."""
        prompt = await self._prompts.create(
            AiPrompt(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                description=description,
                current_version_number="1.0.0",
            )
        )
        version = await self._versions.create(
            AiPromptVersion(
                organization_id=organization_id,
                project_id=project_id,
                prompt_id=prompt.id,
                version_number="1.0.0",
                template=template,
                variables=variables,
                status=PromptStatus.DRAFT,
            )
        )
        return prompt, version

    async def add_version(
        self, prompt_id: UUID, *, template: str, variables: list[str]
    ) -> AiPromptVersion:
        """Add a new draft revision to an existing prompt.

        Raises:
            NotFoundError: If no such prompt exists.
        """
        prompt = await self._prompts.require_by_id(prompt_id)
        existing = await self._versions.list_for_prompt(prompt_id)
        highest = max((version.version_number for version in existing), default="1.0.0")
        return await self._versions.create(
            AiPromptVersion(
                organization_id=prompt.organization_id,
                project_id=prompt.project_id,
                prompt_id=prompt.id,
                version_number=bump_patch(highest),
                template=template,
                variables=variables,
                status=PromptStatus.DRAFT,
            )
        )

    async def approve(
        self, prompt_id: UUID, version_number: str, *, approved_by: UUID | None
    ) -> AiPromptVersion:
        """Approve a revision and make it the prompt's current version.

        Raises:
            NotFoundError: If no such prompt or revision exists.
            ConflictError: If the revision is archived -- an archived
                revision must be superseded, not silently revived.
        """
        prompt = await self._prompts.require_by_id(prompt_id)
        version = await self._versions.get_version(prompt_id, version_number)
        if version is None:
            raise NotFoundError(f"Prompt {prompt_id!r} has no version {version_number!r}.")
        if version.status is PromptStatus.ARCHIVED:
            raise ConflictError(
                f"Version {version_number!r} of prompt {prompt_id!r} is archived "
                "and cannot be approved."
            )

        version.status = PromptStatus.APPROVED
        version.approved_by = approved_by
        version.approved_at = datetime.now(UTC)
        approved = await self._versions.update(version)

        prompt.current_version_number = version_number
        await self._prompts.update(prompt)
        return approved

    async def rollback(self, prompt_id: UUID, version_number: str) -> AiPrompt:
        """Point a prompt back at an earlier approved revision.

        Raises:
            NotFoundError: If no such prompt or revision exists.
            ConflictError: If that revision was never approved --
                rolling back onto an unreviewed draft would defeat the
                approval gate.
        """
        prompt = await self._prompts.require_by_id(prompt_id)
        version = await self._versions.get_version(prompt_id, version_number)
        if version is None:
            raise NotFoundError(f"Prompt {prompt_id!r} has no version {version_number!r}.")
        if version.status is not PromptStatus.APPROVED:
            raise ConflictError(
                f"Version {version_number!r} of prompt {prompt_id!r} is "
                f"{str(version.status)!r}, not approved; cannot roll back onto it."
            )
        prompt.current_version_number = version_number
        return await self._prompts.update(prompt)

    async def render(self, prompt_id: UUID, variables: dict[str, object]) -> str:
        """Render a prompt's own current approved version.

        Raises:
            NotFoundError: If the prompt or its current version is missing.
            ConflictError: If the current version is not approved.
            ValidationError: If a declared variable was not supplied, or
                the template fails to render.
        """
        prompt = await self._prompts.require_by_id(prompt_id)
        version = await self._versions.get_version(prompt_id, prompt.current_version_number)
        if version is None:
            raise NotFoundError(
                f"Prompt {prompt_id!r} points at missing version "
                f"{prompt.current_version_number!r}."
            )
        if version.status is not PromptStatus.APPROVED:
            raise ConflictError(
                f"Prompt {prompt_id!r} current version "
                f"{prompt.current_version_number!r} is not approved."
            )

        missing = [name for name in version.variables if name not in variables]
        if missing:
            raise ValidationError(
                f"Prompt {prompt_id!r} requires variable(s): {', '.join(sorted(missing))}."
            )

        try:
            return _environment.from_string(version.template).render(**variables)
        except Exception as exc:
            raise ValidationError(
                f"Prompt {prompt_id!r} version {version.version_number!r} "
                f"failed to render: {exc}"
            ) from exc


__all__ = ["PromptService", "bump_patch"]
