"""Notification template creation, editing, versioning, and preview.

Editing a template's live body in place would silently change the
wording of every notification already rendered against the old copy's
promise -- so an update that changes rendered content snapshots the
*previous* content into :class:`~app.models.template
.NotificationTemplateVersion` before applying the change and bumps
``current_version``. The live row on :class:`~app.models.template
.NotificationTemplate` always holds the latest content directly (no
extra join to read "what does this template currently say"); the
version table holds everything that used to be current.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError
from shared_core.notifications.exceptions import TemplateRenderError
from shared_core.notifications.renderer import RenderedNotification

from app.models.enums import NotificationCategory, TemplateFormat
from app.models.template import NotificationTemplate, NotificationTemplateVersion
from app.rendering import engine as rendering_engine
from app.repositories.template import (
    NotificationTemplateRepository,
    NotificationTemplateVersionRepository,
)

_CONTENT_FIELDS = frozenset({"subject_template", "body_template", "format"})
_EDITABLE_FIELDS = frozenset({"name", "description", "category", "is_active"}) | _CONTENT_FIELDS


class TemplateService:
    """Templates: creation, editing, versioning, and preview."""

    def __init__(
        self,
        templates: NotificationTemplateRepository,
        versions: NotificationTemplateVersionRepository,
    ) -> None:
        self._templates = templates
        self._versions = versions

    async def create(
        self,
        organization_id: UUID,
        *,
        template_key: str,
        name: str,
        body_template: str,
        template_format: TemplateFormat = TemplateFormat.PLAIN_TEXT,
        description: str | None = None,
        category: NotificationCategory | None = None,
        locale: str = "en",
        subject_template: str | None = None,
        actor_id: str | None = None,
    ) -> NotificationTemplate:
        """Register a new template, validating its syntax first.

        Raises:
            ValidationError: If the subject or body has invalid Jinja2
                syntax -- a caller-supplied mistake, not caught until
                render time otherwise.
        """
        self._validate_syntax(
            template_key=template_key,
            body_template=body_template,
            template_format=template_format,
            locale=locale,
            subject_template=subject_template,
        )
        return await self._templates.create(
            NotificationTemplate(
                organization_id=organization_id,
                template_key=template_key,
                name=name,
                description=description,
                category=category,
                format=template_format,
                locale=locale,
                subject_template=subject_template,
                body_template=body_template,
                current_version=1,
                created_by=UUID(actor_id) if actor_id else None,
            )
        )

    async def get(self, organization_id: UUID, template_id: UUID) -> NotificationTemplate:
        """One template.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._templates.require_in_org(organization_id, template_id)

    async def get_by_key(
        self, organization_id: UUID, template_key: str, *, locale: str = "en"
    ) -> NotificationTemplate | None:
        """The active template for *template_key*/*locale*, if any."""
        return await self._templates.get_by_key(organization_id, template_key, locale=locale)

    async def list_templates(
        self, organization_id: UUID, *, is_active: bool | None = None
    ) -> list[NotificationTemplate]:
        """Templates registered in this organization."""
        return await self._templates.list_for_org(organization_id, is_active=is_active)

    async def update(
        self,
        organization_id: UUID,
        template_id: UUID,
        *,
        actor_id: str | None = None,
        change_note: str | None = None,
        **fields: Any,
    ) -> NotificationTemplate:
        """Edit a template's editable fields, versioning it if content changed.

        Silently ignores any key in *fields* outside the editable set.

        Raises:
            ValidationError: If a changed subject or body has invalid
                Jinja2 syntax.
        """
        stored = await self._templates.require_in_org(organization_id, template_id)
        # `None` means "the caller did not send this field" -- the route
        # always forwards every `TemplateUpdateRequest` field, set or not,
        # so `field in fields` is true even for ones left out of the
        # request body. Without the `is not None` guard, an update that
        # only touches `name` would still compare `fields["body_template"]
        # (None)` against the stored body and treat that mismatch as a
        # content change, spuriously versioning and bumping every update.
        changed_content = any(
            field in fields
            and fields[field] is not None
            and fields[field] != getattr(stored, field)
            for field in _CONTENT_FIELDS
        )
        if changed_content:
            await self._versions.create(
                NotificationTemplateVersion(
                    organization_id=organization_id,
                    template_id=stored.id,
                    version=stored.current_version,
                    subject_template=stored.subject_template,
                    body_template=stored.body_template,
                    format=stored.format,
                    change_note=change_note,
                )
            )
        for field, value in fields.items():
            if field in _EDITABLE_FIELDS and value is not None:
                setattr(stored, field, value)
        if changed_content:
            self._validate_syntax(
                template_key=stored.template_key,
                body_template=stored.body_template,
                template_format=stored.format,
                locale=stored.locale,
                subject_template=stored.subject_template,
            )
            stored.current_version += 1
        stored.updated_by = UUID(actor_id) if actor_id else None
        return await self._templates.update(stored)

    @staticmethod
    def _validate_syntax(
        *,
        template_key: str,
        body_template: str,
        template_format: TemplateFormat,
        locale: str,
        subject_template: str | None,
    ) -> None:
        """Validate a template's Jinja2 syntax, translating a render-time error into a client one.

        `shared_core.notifications.exceptions.TemplateRenderError` is a
        ``500`` by design there (a stored, previously-valid template
        failing to render is this platform's own fault) -- but here the
        same error is raised against syntax a caller just supplied,
        before anything is stored. That is a validation failure, not an
        internal one, so it is re-raised as :class:`ValidationError`
        (``400``) rather than left to reach the caller as a 500.
        """
        try:
            rendering_engine.validate(
                rendering_engine.to_shared_template(
                    template_key=template_key,
                    body_template=body_template,
                    template_format=template_format,
                    locale=locale,
                    subject_template=subject_template,
                )
            )
        except TemplateRenderError as exc:
            raise ValidationError(str(exc)) from exc

    async def list_versions(
        self, organization_id: UUID, template_id: UUID
    ) -> list[NotificationTemplateVersion]:
        """Every prior retained version of this template."""
        return await self._versions.list_for_template(organization_id, template_id)

    async def preview(
        self, organization_id: UUID, template_id: UUID, variables: dict[str, Any]
    ) -> RenderedNotification:
        """Render a template against *variables* for a non-delivery preview."""
        stored = await self._templates.require_in_org(organization_id, template_id)
        shared_template = rendering_engine.to_shared_template(
            template_key=stored.template_key,
            body_template=stored.body_template,
            template_format=stored.format,
            version=stored.current_version,
            locale=stored.locale,
            subject_template=stored.subject_template,
        )
        return rendering_engine.preview(shared_template, variables)


__all__ = ["TemplateService"]
