"""Report template management with versioning and approval.

Mirrors ``services/ai-assistant-service``'s prompt versioning for the
same reason: a template is executable content that queries production
systems, and running an unreviewed one is exactly what the approval
gate exists to prevent.

**Enum columns return ``str``.** ``ReportTemplate.status`` is annotated
``Mapped[TemplateStatus]`` but stored in a plain ``String``, so a row
loaded from Postgres yields a raw ``str``. Comparing that with ``is``
is ``False`` for *every* stored row -- a mistake that shipped three
dead features elsewhere in this platform before it was caught.
:func:`status_of` normalises once, and every comparison here goes
through it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import ParameterKind, ReportCategory, ReportType, TemplateStatus
from app.models.report_parameter import ReportParameter
from app.models.report_template import ReportTemplate
from app.reports.designer.schema import ReportDefinition, parse_definition
from app.repositories.report_parameter import ReportParameterRepository
from app.repositories.report_template import ReportTemplateRepository

_SEMVER_PARTS = 3


def status_of(template: ReportTemplate) -> TemplateStatus:
    """Return a template's status as a genuine :class:`TemplateStatus`.

    See this module's docstring for why this exists rather than
    comparing the attribute directly.
    """
    status = template.status
    return status if isinstance(status, TemplateStatus) else TemplateStatus(status)


def bump_minor(version_number: str) -> str:
    """Return the next minor version after *version_number*.

    Falls back to appending rather than raising on a malformed input: a
    hand-edited version string should not make a template permanently
    un-versionable.
    """
    parts = version_number.split(".")
    if len(parts) != _SEMVER_PARTS or not all(part.isdigit() for part in parts):
        return f"{version_number}.1"
    major, minor, _patch = (int(part) for part in parts)
    return f"{major}.{minor + 1}.0"


def validate_definition(raw: dict[str, Any]) -> ReportDefinition:
    """Parse a designer document, raising the platform's own error.

    Pydantic's own exception type is converted at this boundary so
    callers -- and the HTTP layer -- see one consistent validation
    error rather than a library type leaking outward.

    Raises:
        ValidationError: If the definition is malformed.
    """
    try:
        return parse_definition(raw)
    except PydanticValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise ValidationError(f"Invalid report definition: {problems}") from exc


class ReportTemplateService:
    """Creates, versions, approves, and reads report templates."""

    def __init__(
        self, templates: ReportTemplateRepository, parameters: ReportParameterRepository
    ) -> None:
        self._templates = templates
        self._parameters = parameters

    async def get_by_id(self, template_id: UUID) -> ReportTemplate:
        """Return one template.

        Raises:
            NotFoundError: If no such template exists.
        """
        return await self._templates.require_by_id(template_id)

    async def list_for_org(
        self, organization_id: UUID, *, category: ReportCategory | None = None
    ) -> list[ReportTemplate]:
        """Every template for an organization."""
        return await self._templates.list_for_org(organization_id, category=category)

    async def list_versions(self, organization_id: UUID, name: str) -> list[ReportTemplate]:
        """Every version of one named template."""
        return await self._templates.list_versions(organization_id, name)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        description: str | None,
        category: ReportCategory,
        report_type: ReportType,
        definition: dict[str, Any],
        branding: dict[str, Any] | None = None,
        parameters: list[dict[str, Any]] | None = None,
        category_id: UUID | None = None,
    ) -> tuple[ReportTemplate, list[ReportParameter]]:
        """Create a template's first draft version.

        Raises:
            ValidationError: If the definition or a parameter is malformed.
            ConflictError: If this template name already exists.
        """
        validate_definition(definition)
        existing = await self._templates.list_versions(organization_id, name)
        if existing:
            raise ConflictError(f"A template named {name!r} already exists; add a version instead.")

        template = await self._templates.create(
            ReportTemplate(
                organization_id=organization_id,
                project_id=project_id,
                category_id=category_id,
                name=name,
                description=description,
                category=category,
                report_type=report_type,
                version_number="1.0.0",
                status=TemplateStatus.DRAFT,
                definition=definition,
                branding=branding or {},
            )
        )
        declared = await self._replace_parameters(template.id, organization_id, parameters or [])
        return template, declared

    async def add_version(
        self,
        template_id: UUID,
        *,
        definition: dict[str, Any],
        branding: dict[str, Any] | None = None,
        parameters: list[dict[str, Any]] | None = None,
    ) -> tuple[ReportTemplate, list[ReportParameter]]:
        """Add a new draft version of an existing template.

        Raises:
            NotFoundError: If no such template exists.
            ValidationError: If the definition is malformed.
        """
        validate_definition(definition)
        current = await self._templates.require_by_id(template_id)
        siblings = await self._templates.list_versions(current.organization_id, current.name)
        highest = max(
            (sibling.version_number for sibling in siblings), default=current.version_number
        )

        version = await self._templates.create(
            ReportTemplate(
                organization_id=current.organization_id,
                project_id=current.project_id,
                category_id=current.category_id,
                name=current.name,
                description=current.description,
                category=current.category,
                report_type=current.report_type,
                version_number=bump_minor(highest),
                status=TemplateStatus.DRAFT,
                definition=definition,
                branding=branding if branding is not None else current.branding,
            )
        )
        declared = await self._replace_parameters(
            version.id, current.organization_id, parameters or []
        )
        return version, declared

    async def approve(self, template_id: UUID, *, approved_by: UUID | None) -> ReportTemplate:
        """Approve a template version, making it usable.

        Raises:
            NotFoundError: If no such template exists.
            ConflictError: If the version is archived -- an archived
                version must be superseded, not silently revived.
        """
        template = await self._templates.require_by_id(template_id)
        if status_of(template) is TemplateStatus.ARCHIVED:
            raise ConflictError(
                f"Template version {template.version_number!r} is archived and "
                "cannot be approved."
            )
        template.status = TemplateStatus.APPROVED
        template.approved_by = approved_by
        template.approved_at = datetime.now(UTC)
        return await self._templates.update(template)

    async def archive(self, template_id: UUID) -> ReportTemplate:
        """Archive a template version so it can no longer be used.

        Raises:
            NotFoundError: If no such template exists.
        """
        template = await self._templates.require_by_id(template_id)
        template.status = TemplateStatus.ARCHIVED
        return await self._templates.update(template)

    async def resolve_for_execution(self, template_id: UUID) -> ReportTemplate:
        """Return a template, refusing one that is not approved.

        Raises:
            NotFoundError: If no such template exists.
            ConflictError: If the version is not approved. Running an
                unreviewed template against production data is exactly
                what the gate prevents.
        """
        template = await self._templates.require_by_id(template_id)
        status = status_of(template)
        if status is not TemplateStatus.APPROVED:
            raise ConflictError(
                f"Template {template.name!r} version {template.version_number!r} is "
                f"{str(status)!r}, not approved; it cannot be used to generate a report."
            )
        return template

    async def latest_approved(self, organization_id: UUID, name: str) -> ReportTemplate:
        """The newest approved version of a named template.

        Raises:
            NotFoundError: If no approved version exists.
        """
        template = await self._templates.get_latest_approved(organization_id, name)
        if template is None:
            raise NotFoundError(f"No approved version of template {name!r} exists.")
        return template

    async def list_parameters(self, template_id: UUID) -> list[ReportParameter]:
        """Every parameter a template declares."""
        return await self._parameters.list_for_template(template_id)

    async def _replace_parameters(
        self, template_id: UUID, organization_id: UUID, declarations: list[dict[str, Any]]
    ) -> list[ReportParameter]:
        """Replace a template's parameter set wholesale.

        Replacing rather than merging means a parameter removed from
        the definition genuinely disappears, instead of lingering and
        being silently required by a later run.

        Raises:
            ValidationError: If a declaration is malformed or duplicated.
        """
        await self._parameters.delete_for_template(template_id)
        seen: set[str] = set()
        created: list[ReportParameter] = []

        for order, declaration in enumerate(declarations):
            key = str(declaration.get("key", "")).strip()
            if not key:
                raise ValidationError("Every report parameter requires a 'key'.")
            if key in seen:
                raise ValidationError(f"Duplicate report parameter key {key!r}.")
            seen.add(key)

            try:
                kind = ParameterKind(declaration.get("kind", ParameterKind.STRING))
            except ValueError as exc:
                valid = ", ".join(sorted(str(member) for member in ParameterKind))
                raise ValidationError(
                    f"Parameter {key!r} has unknown kind "
                    f"{declaration.get('kind')!r}. Valid: {valid}."
                ) from exc

            created.append(
                await self._parameters.create(
                    ReportParameter(
                        organization_id=organization_id,
                        template_id=template_id,
                        key=key,
                        label=str(declaration.get("label") or key),
                        description=declaration.get("description"),
                        kind=kind,
                        required=bool(declaration.get("required", False)),
                        default_value=declaration.get("default_value"),
                        allowed_values=list(declaration.get("allowed_values") or []),
                        display_order=int(declaration.get("display_order", order)),
                    )
                )
            )
        return created


__all__ = ["ReportTemplateService", "bump_minor", "status_of", "validate_definition"]
