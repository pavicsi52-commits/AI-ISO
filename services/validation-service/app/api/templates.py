"""``/validation-templates``. Per docs/043 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, TemplateSvc
from app.models.validation_template import ValidationTemplate
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.template import ValidationTemplateCreateRequest, ValidationTemplateResponse

router = APIRouter(prefix="/validation-templates", tags=["Validation Templates"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def template_to_response(template: ValidationTemplate) -> ValidationTemplateResponse:
    return ValidationTemplateResponse(
        id=template.id,
        organization_id=template.organization_id,
        name=template.name,
        description=template.description,
        profile_type=template.profile_type,
        template_content=template.template_content,
        is_system_template=template.is_system_template,
        authored_by=template.authored_by,
    )


@router.get("", response_model=SuccessResponse[list[ValidationTemplateResponse]])
async def list_validation_templates(
    organization_id: UUID, templates: TemplateSvc, _caller: CurrentUserId
) -> SuccessResponse[list[ValidationTemplateResponse]]:
    """List every validation template in *organization_id* ("Reusable Templates")."""
    records = await templates.list_for_org(organization_id)
    data = [template_to_response(record) for record in records]
    return SuccessResponse(message="Validation templates retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[ValidationTemplateResponse], status_code=201)
async def create_validation_template(
    body: ValidationTemplateCreateRequest, templates: TemplateSvc, _caller: CurrentUserId
) -> SuccessResponse[ValidationTemplateResponse]:
    """Create a new reusable validation template."""
    template = await templates.create(
        organization_id=body.organization_id,
        name=body.name,
        description=body.description,
        profile_type=body.profile_type,
        template_content=body.template_content,
        authored_by=str(_caller),
    )
    return SuccessResponse(
        message="Validation template created.", data=template_to_response(template), meta=_meta()
    )


__all__ = ["router", "template_to_response"]
