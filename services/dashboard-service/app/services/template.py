"""Dashboard templates ("Template Library").

A template is validated on write by :mod:`app.templates.schema`, so a
blueprint whose layout references a widget it does not define is
refused at authoring time. That check is what makes
:meth:`TemplateService.apply` safe to run unattended: by the time a
template is applied, it is already known to instantiate something that
renders.

**Applying a template goes through the dashboard service**, not
straight to the repositories. Widgets added this way get the same
render-ability validation, the same layout reconciliation, and the same
``WidgetAdded`` events as ones added by hand -- a template that
bypassed them would be a second, quieter way to create dashboards that
behave differently.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError

from app.models.dashboard import Dashboard
from app.models.dashboard_template import DashboardTemplate
from app.models.enums import DashboardType, DashboardVisibility
from app.repositories.dashboard_template import DashboardTemplateRepository
from app.services.dashboard import DashboardService
from app.templates.schema import TemplateDefinition, parse_template


def type_of(template: DashboardTemplate) -> DashboardType:
    """A template's dashboard type as a genuine enum member.

    ``dashboard_type`` is annotated ``Mapped[DashboardType]`` but stored
    in a ``String``, so a row loaded from Postgres yields a raw ``str``.
    """
    value = template.dashboard_type
    return value if isinstance(value, DashboardType) else DashboardType(value)


class TemplateService:
    """Stores, validates, and applies dashboard templates."""

    def __init__(
        self, templates: DashboardTemplateRepository, dashboards: DashboardService
    ) -> None:
        self._templates = templates
        self._dashboards = dashboards

    async def list_for_org(self, organization_id: UUID) -> list[DashboardTemplate]:
        """Every template available to an organization."""
        return await self._templates.list_for_org(organization_id)

    async def get_by_id(self, template_id: UUID) -> DashboardTemplate:
        """Return one template.

        Raises:
            NotFoundError: If no such template exists.
        """
        return await self._templates.require_by_id(template_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None = None,
        slug: str,
        name: str,
        description: str | None = None,
        definition: dict[str, Any],
        is_system: bool = False,
    ) -> DashboardTemplate:
        """Store a validated template.

        Raises:
            ConflictError: If the slug is already used.
            ValidationError: If the definition is incoherent.
        """
        if await self._templates.get_by_slug(organization_id, slug) is not None:
            raise ConflictError(f"A template with slug {slug!r} already exists.")
        parsed = self._parse(definition)
        return await self._templates.create(
            DashboardTemplate(
                organization_id=organization_id,
                project_id=project_id,
                slug=slug,
                name=name,
                description=description or parsed.description,
                dashboard_type=parsed.dashboard_type,
                definition=parsed.model_dump(mode="json"),
                is_system=is_system,
            )
        )

    async def update(
        self,
        template_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        definition: dict[str, Any] | None = None,
    ) -> DashboardTemplate:
        """Update a template in place.

        Raises:
            NotFoundError: If no such template exists.
            ConflictError: If it is a built-in system template.
            ValidationError: If the new definition is incoherent.
        """
        template = await self._templates.require_by_id(template_id)
        if template.is_system:
            raise ConflictError(
                "Built-in templates cannot be edited; copy one and change the copy instead."
            )
        if name is not None:
            template.name = name
        if description is not None:
            template.description = description
        if definition is not None:
            parsed = self._parse(definition)
            template.definition = parsed.model_dump(mode="json")
            template.dashboard_type = parsed.dashboard_type
        return await self._templates.update(template)

    async def delete(self, template_id: UUID, *, deleted_by: UUID | None = None) -> None:
        """Soft-delete a template.

        Raises:
            NotFoundError: If no such template exists.
            ConflictError: If it is a built-in system template.
        """
        template = await self._templates.require_by_id(template_id)
        if template.is_system:
            raise ConflictError("Built-in templates cannot be deleted.")
        await self._templates.delete(template_id, deleted_by=deleted_by)

    async def capture(
        self,
        dashboard_id: UUID,
        *,
        slug: str,
        name: str,
        description: str | None = None,
    ) -> DashboardTemplate:
        """Turn an existing dashboard into a reusable template.

        Captures the widgets and the desktop layout as they stand. The
        result goes back through :meth:`create`, so a dashboard that
        somehow holds an incoherent arrangement cannot become a template
        that spreads it.

        Raises:
            NotFoundError: If the dashboard does not exist.
            ConflictError: If the slug is already used.
        """
        dashboard = await self._dashboards.get_by_id(dashboard_id)
        widgets = await self._dashboards.list_widgets(dashboard_id)
        layout = await self._dashboards.get_layout(dashboard_id)
        definition = {
            "dashboard_type": str(dashboard.dashboard_type),
            "description": description or dashboard.description,
            "refresh_seconds": dashboard.refresh_seconds,
            "default_filters": list(dashboard.default_filters or []),
            "widgets": [
                {
                    "widget_key": widget.widget_key,
                    "title": widget.title,
                    "widget_type": str(widget.widget_type),
                    "query": dict(widget.query or {}),
                    "options": dict(widget.options or {}),
                }
                for widget in widgets
            ],
            "layouts": [{"breakpoint": "desktop", "grid": layout.model_dump(mode="json")}],
        }
        return await self.create(
            organization_id=dashboard.organization_id,
            project_id=dashboard.project_id,
            slug=slug,
            name=name,
            description=description,
            definition=definition,
        )

    async def apply(
        self,
        template_id: UUID,
        *,
        organization_id: UUID,
        project_id: UUID | None = None,
        slug: str,
        name: str,
        owner_id: UUID | None = None,
        visibility: DashboardVisibility = DashboardVisibility.PRIVATE,
    ) -> Dashboard:
        """Instantiate a template as a new dashboard.

        Raises:
            NotFoundError: If the template does not exist.
            ConflictError: If the dashboard slug is already used.
            ValidationError: If the stored definition is unusable.
        """
        template = await self._templates.require_by_id(template_id)
        parsed = self._parse(template.definition or {})

        dashboard = await self._dashboards.create(
            organization_id=organization_id,
            project_id=project_id,
            slug=slug,
            name=name,
            description=parsed.description,
            dashboard_type=parsed.dashboard_type,
            visibility=visibility,
            owner_id=owner_id,
            default_filters=parsed.default_filters,
            refresh_seconds=parsed.refresh_seconds,
        )
        for widget in parsed.widgets:
            await self._dashboards.add_widget(
                dashboard.id, definition=widget.model_dump(mode="json"), actor_id=owner_id
            )
        for layout in parsed.layouts:
            await self._dashboards.save_layout(
                dashboard.id,
                breakpoint_=layout.breakpoint,
                placements=[
                    placement.model_dump(mode="json") for placement in layout.grid.placements
                ],
                columns=layout.grid.columns,
                row_height=layout.grid.row_height,
                name=f"From template {template.name!r}",
                actor_id=owner_id,
            )

        template.applied_count += 1
        await self._templates.update(template)
        return dashboard

    def definition_of(self, template: DashboardTemplate) -> TemplateDefinition:
        """Reassemble a stored template into its validated document."""
        return self._parse(template.definition or {})

    @staticmethod
    def _parse(raw: dict[str, Any]) -> TemplateDefinition:
        """Parse a template document, raising the platform's own error."""
        try:
            return parse_template(raw)
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(f"Invalid dashboard template: {exc}") from exc


__all__ = ["TemplateService", "type_of"]
