"""Template management (docs/055 "TEMPLATE MANAGEMENT")."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, TemplateSvc
from app.models.enums import AuditAction
from app.schemas.notification import (
    TemplateCreateRequest,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    TemplateResponse,
    TemplateUpdateRequest,
    TemplateVersionResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/notifications/templates", tags=["Templates"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[TemplateResponse]], summary="List templates")
async def list_templates(
    organization_id: UUID,
    templates: TemplateSvc,
    is_active: Annotated[bool | None, Query()] = None,
) -> SuccessResponse[list[TemplateResponse]]:
    """Templates registered in this organization."""
    rows = await templates.list_templates(organization_id, is_active=is_active)
    return SuccessResponse(
        message="Templates listed.",
        data=[TemplateResponse.model_validate(row) for row in rows],
        meta=_meta(),
    )


@router.get("/{template_id}", response_model=SuccessResponse[TemplateResponse], summary="Get a template")
async def get_template(
    organization_id: UUID, template_id: UUID, templates: TemplateSvc
) -> SuccessResponse[TemplateResponse]:
    """One template."""
    found = await templates.get(organization_id, template_id)
    return SuccessResponse(
        message="Template found.", data=TemplateResponse.model_validate(found), meta=_meta()
    )


@router.post(
    "",
    response_model=SuccessResponse[TemplateResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new template",
)
async def create_template(
    organization_id: UUID,
    body: TemplateCreateRequest,
    templates: TemplateSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[TemplateResponse]:
    """Register a new template, validating its syntax first."""
    created = await templates.create(
        organization_id,
        template_key=body.template_key,
        name=body.name,
        body_template=body.body_template,
        template_format=body.format,
        description=body.description,
        category=body.category,
        locale=body.locale,
        subject_template=body.subject_template,
        actor_id=str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.TEMPLATE_CREATED,
        entity_type="template",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Registered template {created.template_key!r}.",
    )
    return SuccessResponse(
        message="Template registered.", data=TemplateResponse.model_validate(created), meta=_meta()
    )


@router.put(
    "/{template_id}", response_model=SuccessResponse[TemplateResponse], summary="Update a template"
)
async def update_template(
    organization_id: UUID,
    template_id: UUID,
    body: TemplateUpdateRequest,
    templates: TemplateSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[TemplateResponse]:
    """Edit a template's editable fields, versioning it if content changed."""
    updated = await templates.update(
        organization_id,
        template_id,
        actor_id=str(caller),
        change_note=body.change_note,
        name=body.name,
        description=body.description,
        category=body.category,
        body_template=body.body_template,
        subject_template=body.subject_template,
        format=body.format,
        is_active=body.is_active,
    )
    await audit.record(
        organization_id,
        action=AuditAction.TEMPLATE_UPDATED,
        entity_type="template",
        entity_id=updated.id,
        actor_id=str(caller),
        summary=f"Updated template {updated.template_key!r}.",
    )
    return SuccessResponse(
        message="Template updated.", data=TemplateResponse.model_validate(updated), meta=_meta()
    )


@router.get(
    "/{template_id}/versions",
    response_model=SuccessResponse[list[TemplateVersionResponse]],
    summary="List a template's prior versions",
)
async def list_template_versions(
    organization_id: UUID, template_id: UUID, templates: TemplateSvc
) -> SuccessResponse[list[TemplateVersionResponse]]:
    """Every prior retained version of this template ("Template Versioning")."""
    rows = await templates.list_versions(organization_id, template_id)
    return SuccessResponse(
        message="Template versions listed.",
        data=[TemplateVersionResponse.model_validate(row) for row in rows],
        meta=_meta(),
    )


@router.post(
    "/{template_id}/preview",
    response_model=SuccessResponse[TemplatePreviewResponse],
    summary="Render a template against sample variables",
)
async def preview_template(
    organization_id: UUID, template_id: UUID, body: TemplatePreviewRequest, templates: TemplateSvc
) -> SuccessResponse[TemplatePreviewResponse]:
    """Render a template for a non-delivery preview ("Preview", "Testing")."""
    rendered = await templates.preview(organization_id, template_id, body.variables)
    return SuccessResponse(
        message="Template rendered.",
        data=TemplatePreviewResponse(
            subject=rendered.subject, body=rendered.body, format=rendered.format
        ),
        meta=_meta(),
    )


__all__ = ["router"]
