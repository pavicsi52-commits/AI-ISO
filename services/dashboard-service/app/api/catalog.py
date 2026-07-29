"""Theme and template endpoints.

``GET``/``POST /dashboards/templates`` are the paths docs/048 names.
Themes live alongside at ``/dashboards/themes`` -- both are literal
segments declared in their own router, which is included *before*
:mod:`app.api.dashboards` so they can never be parsed as a dashboard
id.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, TemplateSvc, ThemeSvc
from app.models.enums import AuditAction
from app.schemas.catalog import (
    ContrastFindingModel,
    TemplateApplyRequest,
    TemplateCaptureRequest,
    TemplateCreateRequest,
    TemplateSummary,
    ThemeCreateRequest,
    ThemeResponse,
    ThemeSummary,
    ThemeUpdateRequest,
)
from app.schemas.dashboard import DashboardSummary
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/dashboards", tags=["Themes & Templates"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


# ---- templates -----------------------------------------------------


@router.get(
    "/templates",
    response_model=SuccessResponse[list[TemplateSummary]],
    summary="List dashboard templates",
)
async def list_templates(
    organization_id: UUID, templates: TemplateSvc
) -> SuccessResponse[list[TemplateSummary]]:
    """Return every template available to an organization."""
    found = await templates.list_for_org(organization_id)
    return SuccessResponse(
        message=f"Found {len(found)} templates.",
        data=[TemplateSummary.model_validate(one) for one in found],
        meta=_meta(),
    )


@router.post(
    "/templates",
    response_model=SuccessResponse[TemplateSummary],
    status_code=status.HTTP_201_CREATED,
    summary="Create a dashboard template",
)
async def create_template(
    organization_id: UUID,
    body: TemplateCreateRequest,
    templates: TemplateSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[TemplateSummary]:
    """Store a template, validated so it cannot instantiate a broken dashboard."""
    template = await templates.create(
        organization_id=organization_id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        definition=body.definition,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.TEMPLATE_CREATED,
        entity_type="template",
        entity_id=template.id,
        actor_id=caller,
        context={"slug": template.slug},
    )
    return SuccessResponse(
        message=f"Template {template.name!r} created.",
        data=TemplateSummary.model_validate(template),
        meta=_meta(),
    )


@router.post(
    "/templates/capture",
    response_model=SuccessResponse[TemplateSummary],
    status_code=status.HTTP_201_CREATED,
    summary="Turn an existing dashboard into a template",
)
async def capture_template(
    body: TemplateCaptureRequest,
    templates: TemplateSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[TemplateSummary]:
    """Capture a dashboard's widgets and desktop layout as a template."""
    template = await templates.capture(
        body.dashboard_id, slug=body.slug, name=body.name, description=body.description
    )
    await audit.record(
        organization_id=template.organization_id,
        action=AuditAction.TEMPLATE_CREATED,
        entity_type="template",
        entity_id=template.id,
        actor_id=caller,
        context={"captured_from": str(body.dashboard_id)},
    )
    return SuccessResponse(
        message=f"Template {template.name!r} captured.",
        data=TemplateSummary.model_validate(template),
        meta=_meta(),
    )


@router.post(
    "/templates/{template_id}/apply",
    response_model=SuccessResponse[DashboardSummary],
    status_code=status.HTTP_201_CREATED,
    summary="Instantiate a template as a new dashboard",
)
async def apply_template(
    template_id: UUID,
    organization_id: UUID,
    body: TemplateApplyRequest,
    templates: TemplateSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[DashboardSummary]:
    """Create a dashboard from a template, widgets and layout included."""
    dashboard = await templates.apply(
        template_id,
        organization_id=organization_id,
        project_id=body.project_id,
        slug=body.slug,
        name=body.name,
        owner_id=caller,
        visibility=body.visibility,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.TEMPLATE_APPLIED,
        entity_type="dashboard",
        entity_id=dashboard.id,
        actor_id=caller,
        context={"template_id": str(template_id)},
    )
    return SuccessResponse(
        message=f"Dashboard {dashboard.name!r} created from template.",
        data=DashboardSummary.model_validate(dashboard),
        meta=_meta(),
    )


@router.delete(
    "/templates/{template_id}",
    response_model=SuccessResponse[dict[str, str]],
    summary="Delete a template",
)
async def delete_template(
    template_id: UUID, templates: TemplateSvc, caller: CurrentUserId
) -> SuccessResponse[dict[str, str]]:
    """Soft-delete a template. Built-in templates are refused."""
    await templates.delete(template_id, deleted_by=caller)
    return SuccessResponse(
        message="Template deleted.", data={"template_id": str(template_id)}, meta=_meta()
    )


# ---- themes --------------------------------------------------------


@router.get(
    "/themes",
    response_model=SuccessResponse[list[ThemeSummary]],
    summary="List dashboard themes",
)
async def list_themes(
    organization_id: UUID, themes: ThemeSvc
) -> SuccessResponse[list[ThemeSummary]]:
    """Return every theme available to an organization."""
    found = await themes.list_for_org(organization_id)
    return SuccessResponse(
        message=f"Found {len(found)} themes.",
        data=[ThemeSummary.model_validate(one) for one in found],
        meta=_meta(),
    )


@router.post(
    "/themes",
    response_model=SuccessResponse[ThemeResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a theme",
)
async def create_theme(
    organization_id: UUID,
    body: ThemeCreateRequest,
    themes: ThemeSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ThemeResponse]:
    """Create a theme, reporting any WCAG AA contrast shortfalls."""
    theme, findings = await themes.create(
        organization_id=organization_id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        mode=body.mode,
        definition=body.definition,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.THEME_CHANGED,
        entity_type="theme",
        entity_id=theme.id,
        actor_id=caller,
        context={"slug": theme.slug, "contrast_findings": len(findings)},
    )
    return SuccessResponse(
        message=(
            f"Theme {theme.name!r} created."
            if not findings
            else f"Theme {theme.name!r} created with {len(findings)} contrast shortfalls."
        ),
        data=ThemeResponse(
            theme=ThemeSummary.model_validate(theme),
            contrast_findings=[
                ContrastFindingModel.model_validate(finding.model_dump()) for finding in findings
            ],
        ),
        meta=_meta(),
    )


@router.put(
    "/themes/{theme_id}",
    response_model=SuccessResponse[ThemeResponse],
    summary="Update a theme",
)
async def update_theme(
    theme_id: UUID,
    body: ThemeUpdateRequest,
    themes: ThemeSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ThemeResponse]:
    """Update a theme. Built-in themes are refused; copy one instead."""
    theme, findings = await themes.update(
        theme_id,
        name=body.name,
        description=body.description,
        mode=body.mode,
        definition=body.definition,
    )
    await audit.record(
        organization_id=theme.organization_id,
        action=AuditAction.THEME_CHANGED,
        entity_type="theme",
        entity_id=theme.id,
        actor_id=caller,
    )
    return SuccessResponse(
        message="Theme updated.",
        data=ThemeResponse(
            theme=ThemeSummary.model_validate(theme),
            contrast_findings=[
                ContrastFindingModel.model_validate(finding.model_dump()) for finding in findings
            ],
        ),
        meta=_meta(),
    )


@router.get(
    "/themes/{theme_id}/accessibility",
    response_model=SuccessResponse[dict[str, object]],
    summary="Audit a theme's accessibility",
)
async def audit_theme(theme_id: UUID, themes: ThemeSvc) -> SuccessResponse[dict[str, object]]:
    """Report a theme's WCAG standing, pair by pair."""
    theme = await themes.get_by_id(theme_id)
    return SuccessResponse(message="Accessibility audited.", data=themes.audit(theme), meta=_meta())


@router.post(
    "/themes/seed",
    response_model=SuccessResponse[list[ThemeSummary]],
    summary="Seed the built-in themes",
)
async def seed_themes(
    organization_id: UUID, themes: ThemeSvc
) -> SuccessResponse[list[ThemeSummary]]:
    """Ensure the built-in light and dark themes exist. Idempotent."""
    created = await themes.seed_system_themes(organization_id)
    return SuccessResponse(
        message=f"Seeded {len(created)} built-in themes.",
        data=[ThemeSummary.model_validate(one) for one in created],
        meta=_meta(),
    )


@router.delete(
    "/themes/{theme_id}",
    response_model=SuccessResponse[dict[str, str]],
    summary="Delete a theme",
)
async def delete_theme(
    theme_id: UUID, themes: ThemeSvc, caller: CurrentUserId
) -> SuccessResponse[dict[str, str]]:
    """Soft-delete a theme. Built-in themes are refused."""
    await themes.delete(theme_id, deleted_by=caller)
    return SuccessResponse(message="Theme deleted.", data={"theme_id": str(theme_id)}, meta=_meta())


__all__ = ["router"]
