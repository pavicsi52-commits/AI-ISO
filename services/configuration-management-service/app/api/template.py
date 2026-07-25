"""``GET/POST /configurations/templates``. Per docs/039 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, TemplateSvc
from app.models.configuration_template import ConfigurationTemplate
from app.models.enums import ConfigurationType
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.template import ConfigurationTemplateCreateRequest, ConfigurationTemplateResponse

router = APIRouter(prefix="/configurations", tags=["Templates"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def template_to_response(template: ConfigurationTemplate) -> ConfigurationTemplateResponse:
    return ConfigurationTemplateResponse(
        id=template.id,
        organization_id=template.organization_id,
        project_id=template.project_id,
        template_name=template.template_name,
        description=template.description,
        configuration_type=template.configuration_type,
        content=template.content,
        variables_schema=template.variables_schema,
    )


@router.get("/templates", response_model=SuccessResponse[list[ConfigurationTemplateResponse]])
async def list_templates(
    organization_id: UUID,
    templates: TemplateSvc,
    _caller: CurrentUserId,
    configuration_type: ConfigurationType | None = None,
) -> SuccessResponse[list[ConfigurationTemplateResponse]]:
    """List every reusable configuration template in *organization_id*."""
    records = await templates.list_for_org(organization_id, configuration_type=configuration_type)
    data = [template_to_response(record) for record in records]
    return SuccessResponse(message="Configuration templates retrieved.", data=data, meta=_meta())


@router.post(
    "/templates", response_model=SuccessResponse[ConfigurationTemplateResponse], status_code=201
)
async def create_template(
    body: ConfigurationTemplateCreateRequest, templates: TemplateSvc, _caller: CurrentUserId
) -> SuccessResponse[ConfigurationTemplateResponse]:
    """Define a new reusable configuration template."""
    template = await templates.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        template_name=body.template_name,
        description=body.description,
        configuration_type=body.configuration_type,
        content=body.content,
        variables_schema=body.variables_schema,
    )
    return SuccessResponse(
        message="Configuration template created.", data=template_to_response(template), meta=_meta()
    )


__all__ = ["router", "template_to_response"]
