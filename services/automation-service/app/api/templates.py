"""``GET/POST /automation/templates``. Per docs/040 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, TemplateSvc
from app.models.automation_template import AutomationTemplate
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.template import AutomationTemplateCreateRequest, AutomationTemplateResponse

router = APIRouter(prefix="/automation/templates", tags=["Templates"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def template_to_response(template: AutomationTemplate) -> AutomationTemplateResponse:
    return AutomationTemplateResponse(
        id=template.id,
        organization_id=template.organization_id,
        project_id=template.project_id,
        template_name=template.template_name,
        description=template.description,
        playbook_type=template.playbook_type,
        content=template.content,
        variables_schema=template.variables_schema,
    )


@router.get("", response_model=SuccessResponse[list[AutomationTemplateResponse]])
async def list_templates(
    organization_id: UUID, templates: TemplateSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AutomationTemplateResponse]]:
    """List every reusable automation template in *organization_id*."""
    records = await templates.list_for_org(organization_id)
    data = [template_to_response(record) for record in records]
    return SuccessResponse(message="Automation templates retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[AutomationTemplateResponse], status_code=201)
async def create_template(
    body: AutomationTemplateCreateRequest, templates: TemplateSvc, _caller: CurrentUserId
) -> SuccessResponse[AutomationTemplateResponse]:
    """Define a new reusable automation content template."""
    template = await templates.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        template_name=body.template_name,
        description=body.description,
        playbook_type=body.playbook_type,
        content=body.content,
        variables_schema=body.variables_schema,
    )
    return SuccessResponse(
        message="Automation template created.", data=template_to_response(template), meta=_meta()
    )


__all__ = ["router", "template_to_response"]
