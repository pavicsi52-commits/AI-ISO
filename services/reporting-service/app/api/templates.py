"""``/reports/templates`` and ``/reports/categories``."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.exceptions.conflict import ConflictError
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CategoryRepo, CurrentUserId, TemplateSvc
from app.models.enums import AuditAction, ReportCategory
from app.models.report_category import ReportCategoryRecord
from app.models.report_parameter import ReportParameter
from app.models.report_template import ReportTemplate
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.template import (
    CategoryCreateRequest,
    CategoryResponse,
    ParameterResponse,
    TemplateCreateRequest,
    TemplateResponse,
    TemplateVersionRequest,
)

router = APIRouter(prefix="/reports", tags=["Report Templates"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def template_to_response(template: ReportTemplate) -> TemplateResponse:
    """Map a template row onto its own response schema."""
    return TemplateResponse(
        id=template.id,
        organization_id=template.organization_id,
        project_id=template.project_id,
        category_id=template.category_id,
        name=template.name,
        description=template.description,
        category=template.category,
        report_type=template.report_type,
        version_number=template.version_number,
        status=template.status,
        definition=template.definition,
        branding=template.branding,
        is_system=template.is_system,
        approved_by=template.approved_by,
        approved_at=template.approved_at,
    )


def parameter_to_response(parameter: ReportParameter) -> ParameterResponse:
    """Map a parameter row onto its own response schema."""
    return ParameterResponse(
        id=parameter.id,
        template_id=parameter.template_id,
        key=parameter.key,
        label=parameter.label,
        description=parameter.description,
        kind=parameter.kind,
        required=parameter.required,
        default_value=parameter.default_value,
        allowed_values=parameter.allowed_values,
        display_order=parameter.display_order,
    )


def category_to_response(record: ReportCategoryRecord) -> CategoryResponse:
    """Map a category row onto its own response schema."""
    return CategoryResponse(
        id=record.id,
        organization_id=record.organization_id,
        category=record.category,
        slug=record.slug,
        name=record.name,
        description=record.description,
        display_order=record.display_order,
        enabled=record.enabled,
    )


@router.get("/templates", response_model=SuccessResponse[list[TemplateResponse]])
async def list_templates(
    organization_id: UUID,
    templates: TemplateSvc,
    _caller: CurrentUserId,
    category: ReportCategory | None = None,
) -> SuccessResponse[list[TemplateResponse]]:
    """Every template version for an organization."""
    records = await templates.list_for_org(organization_id, category=category)
    return SuccessResponse(
        message="Templates retrieved.",
        data=[template_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post("/templates", response_model=SuccessResponse[TemplateResponse], status_code=201)
async def create_template(
    body: TemplateCreateRequest,
    templates: TemplateSvc,
    caller: CurrentUserId,
    audit: AuditSvc,
) -> SuccessResponse[TemplateResponse]:
    """Create a template's first draft version.

    The designer document is validated here, so a malformed template is
    rejected at authoring time rather than inside a scheduled run.

    Raises:
        ValidationError: If the definition or a parameter is malformed.
        ConflictError: If a template with this name already exists.
    """
    template, _parameters = await templates.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        category=body.category,
        report_type=body.report_type,
        definition=body.definition,
        branding=body.branding,
        parameters=[parameter.model_dump() for parameter in body.parameters],
        category_id=body.category_id,
    )
    await audit.record(
        organization_id=body.organization_id,
        action=AuditAction.TEMPLATE_CREATED,
        entity_type="ReportTemplate",
        entity_id=template.id,
        actor_id=caller,
        reason=f"Template {body.name!r} created.",
    )
    return SuccessResponse(
        message="Template created.", data=template_to_response(template), meta=_meta()
    )


@router.get("/templates/{template_id}", response_model=SuccessResponse[TemplateResponse])
async def get_template(
    template_id: UUID, templates: TemplateSvc, _caller: CurrentUserId
) -> SuccessResponse[TemplateResponse]:
    """Return one template version.

    Raises:
        NotFoundError: If no such template exists.
    """
    template = await templates.get_by_id(template_id)
    return SuccessResponse(
        message="Template retrieved.", data=template_to_response(template), meta=_meta()
    )


@router.get(
    "/templates/{template_id}/parameters",
    response_model=SuccessResponse[list[ParameterResponse]],
)
async def list_template_parameters(
    template_id: UUID, templates: TemplateSvc, _caller: CurrentUserId
) -> SuccessResponse[list[ParameterResponse]]:
    """Every parameter a template declares."""
    records = await templates.list_parameters(template_id)
    return SuccessResponse(
        message="Template parameters retrieved.",
        data=[parameter_to_response(record) for record in records],
        meta=_meta(),
    )


@router.get(
    "/templates/{template_id}/versions",
    response_model=SuccessResponse[list[TemplateResponse]],
)
async def list_template_versions(
    template_id: UUID, templates: TemplateSvc, _caller: CurrentUserId
) -> SuccessResponse[list[TemplateResponse]]:
    """Every version of the named template this version belongs to.

    Raises:
        NotFoundError: If no such template exists.
    """
    template = await templates.get_by_id(template_id)
    records = await templates.list_versions(template.organization_id, template.name)
    return SuccessResponse(
        message="Template versions retrieved.",
        data=[template_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post(
    "/templates/{template_id}/versions",
    response_model=SuccessResponse[TemplateResponse],
    status_code=201,
)
async def add_template_version(
    template_id: UUID,
    body: TemplateVersionRequest,
    templates: TemplateSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[TemplateResponse]:
    """Add a new draft version of an existing template.

    Raises:
        NotFoundError: If no such template exists.
        ValidationError: If the definition is malformed.
    """
    version, _parameters = await templates.add_version(
        template_id,
        definition=body.definition,
        branding=body.branding,
        parameters=[parameter.model_dump() for parameter in body.parameters],
    )
    return SuccessResponse(
        message="Template version created.",
        data=template_to_response(version),
        meta=_meta(),
    )


@router.post("/templates/{template_id}/approve", response_model=SuccessResponse[TemplateResponse])
async def approve_template(
    template_id: UUID, templates: TemplateSvc, caller: CurrentUserId, audit: AuditSvc
) -> SuccessResponse[TemplateResponse]:
    """Approve a template version, making it usable for generation.

    Raises:
        NotFoundError: If no such template exists.
        ConflictError: If the version is archived.
    """
    template = await templates.approve(template_id, approved_by=caller)
    await audit.record(
        organization_id=template.organization_id,
        action=AuditAction.TEMPLATE_APPROVED,
        entity_type="ReportTemplate",
        entity_id=template.id,
        actor_id=caller,
        reason=f"Version {template.version_number!r} approved.",
    )
    return SuccessResponse(
        message="Template approved.", data=template_to_response(template), meta=_meta()
    )


@router.post("/templates/{template_id}/archive", response_model=SuccessResponse[TemplateResponse])
async def archive_template(
    template_id: UUID, templates: TemplateSvc, caller: CurrentUserId, audit: AuditSvc
) -> SuccessResponse[TemplateResponse]:
    """Archive a template version so it can no longer be used.

    Raises:
        NotFoundError: If no such template exists.
    """
    template = await templates.archive(template_id)
    await audit.record(
        organization_id=template.organization_id,
        action=AuditAction.TEMPLATE_DELETED,
        entity_type="ReportTemplate",
        entity_id=template.id,
        actor_id=caller,
        reason=f"Version {template.version_number!r} archived.",
    )
    return SuccessResponse(
        message="Template archived.", data=template_to_response(template), meta=_meta()
    )


@router.get("/categories", response_model=SuccessResponse[list[CategoryResponse]])
async def list_categories(
    organization_id: UUID, categories: CategoryRepo, _caller: CurrentUserId
) -> SuccessResponse[list[CategoryResponse]]:
    """Every report category for an organization, in display order."""
    records = await categories.list_for_org(organization_id)
    return SuccessResponse(
        message="Report categories retrieved.",
        data=[category_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post("/categories", response_model=SuccessResponse[CategoryResponse], status_code=201)
async def create_category(
    body: CategoryCreateRequest, categories: CategoryRepo, _caller: CurrentUserId
) -> SuccessResponse[CategoryResponse]:
    """Create a report category.

    The slug is checked first so a duplicate returns a clear conflict
    rather than a raw integrity error from the unique constraint.

    Raises:
        ConflictError: If the slug is already used in this organization.
    """
    existing = await categories.get_by_slug(body.organization_id, body.slug)
    if existing is not None:
        raise ConflictError(f"A report category with slug {body.slug!r} already exists.")
    record = await categories.create(
        ReportCategoryRecord(
            organization_id=body.organization_id,
            project_id=body.project_id,
            category=body.category,
            slug=body.slug,
            name=body.name,
            description=body.description,
            display_order=body.display_order,
        )
    )
    return SuccessResponse(
        message="Report category created.", data=category_to_response(record), meta=_meta()
    )


__all__ = [
    "category_to_response",
    "parameter_to_response",
    "router",
    "template_to_response",
]
