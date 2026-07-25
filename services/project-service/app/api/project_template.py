"""``/projects/templates``. Per docs/034 REST list.

Organization-scoped, not project-scoped -- see
``app/models/project_template.py``'s own docstring for why. Creation
requires only authentication (any authenticated caller may contribute
a reusable template for an organization they specify), the same
low-friction "reusable content, not a security-sensitive resource"
treatment ``services/organization-service``'s own directory-level
``GET /organizations`` establishes.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, TemplateSvc
from app.models.project_template import ProjectTemplate
from app.schemas.project_template import ProjectTemplateCreateRequest, ProjectTemplateResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/projects/templates", tags=["Project Templates"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(template: ProjectTemplate) -> ProjectTemplateResponse:
    return ProjectTemplateResponse(
        id=template.id,
        organization_id=template.organization_id,
        name=template.name,
        description=template.description,
        category=template.category,
        template_version=template.template_version,
        is_system=template.is_system,
        definition=template.definition,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.get("", response_model=SuccessResponse[list[ProjectTemplateResponse]])
async def list_templates(
    organization_id: Annotated[UUID, Query()], templates: TemplateSvc, _caller: CurrentUserId
) -> SuccessResponse[list[ProjectTemplateResponse]]:
    """List every template available to *organization_id*."""
    records = await templates.list_for_org(organization_id)
    return SuccessResponse(
        message="Templates retrieved.", data=[_to_response(t) for t in records], meta=_meta()
    )


@router.post("", response_model=SuccessResponse[ProjectTemplateResponse], status_code=201)
async def create_template(
    body: ProjectTemplateCreateRequest, templates: TemplateSvc, _caller: CurrentUserId
) -> SuccessResponse[ProjectTemplateResponse]:
    """Create a new reusable project template ("Create", "Template Versioning")."""
    template = await templates.create(
        body.organization_id,
        name=body.name,
        description=body.description,
        category=body.category,
        template_version=body.template_version,
        definition=body.definition,
    )
    return SuccessResponse(message="Template created.", data=_to_response(template), meta=_meta())


__all__ = ["router"]
