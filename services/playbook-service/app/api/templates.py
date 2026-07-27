"""``GET/POST /playbooks/templates``. Per docs/041 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, TemplateSvc
from app.models.playbook_template import PlaybookTemplate
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.template import PlaybookTemplateCreateRequest, PlaybookTemplateResponse

router = APIRouter(prefix="/playbooks/templates", tags=["Templates"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def template_to_response(template: PlaybookTemplate) -> PlaybookTemplateResponse:
    return PlaybookTemplateResponse(
        id=template.id,
        organization_id=template.organization_id,
        template_name=template.template_name,
        description=template.description,
        content_type=template.content_type,
        content=template.content,
        variables_schema=template.variables_schema,
    )


@router.get("", response_model=SuccessResponse[list[PlaybookTemplateResponse]])
async def list_templates(
    organization_id: UUID, templates: TemplateSvc, _caller: CurrentUserId
) -> SuccessResponse[list[PlaybookTemplateResponse]]:
    """List every reusable playbook content template in *organization_id*."""
    records = await templates.list_for_org(organization_id)
    data = [template_to_response(record) for record in records]
    return SuccessResponse(message="Playbook templates retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[PlaybookTemplateResponse], status_code=201)
async def create_template(
    body: PlaybookTemplateCreateRequest, templates: TemplateSvc, _caller: CurrentUserId
) -> SuccessResponse[PlaybookTemplateResponse]:
    """Define a new reusable playbook content template."""
    template = await templates.create(
        organization_id=body.organization_id,
        template_name=body.template_name,
        description=body.description,
        content_type=body.content_type,
        content=body.content,
        variables_schema=body.variables_schema,
    )
    return SuccessResponse(
        message="Playbook template created.", data=template_to_response(template), meta=_meta()
    )


__all__ = ["router", "template_to_response"]
