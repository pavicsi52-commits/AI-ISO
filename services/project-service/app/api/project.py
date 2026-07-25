"""``/projects``. Per docs/034 REST list.

``POST /projects`` requires only authentication -- there is no existing
membership to check for a brand-new project (the same bootstrap problem
``services/organization-service``'s own ``POST /organizations`` handler
documents), so any authenticated caller may create one, automatically
becoming its Owner. Every other mutation requires the caller hold at
least the Administrator rank in the target project
(:func:`app.api.deps.require_project_admin`).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, MemberSvc, ProjSvc, require_project_admin
from app.models.enums import ProjectVisibility
from app.models.project import Project
from app.models.project_role import OWNER_ROLE_ID
from app.schemas.project import (
    ProjectArchiveRequest,
    ProjectCloneRequest,
    ProjectCreateRequest,
    ProjectPatchRequest,
    ProjectResponse,
    ProjectUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/projects", tags=["Projects"])

_RequireAdmin = Depends(require_project_admin)


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def project_to_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        organization_id=project.organization_id,
        name=project.name,
        display_name=project.display_name,
        description=project.description,
        code=project.code,
        status=project.status,
        owner_id=project.owner_id,
        visibility=project.visibility,
        default_language=project.default_language,
        timezone=project.timezone,
        category=project.category,
        priority=project.priority,
        archived_at=project.archived_at,
        metadata=project.metadata_,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get("", response_model=SuccessResponse[list[ProjectResponse]])
async def list_projects(
    organization_id: UUID, projects: ProjSvc, members: MemberSvc, caller: CurrentUserId
) -> SuccessResponse[list[ProjectResponse]]:
    """List every project in *organization_id* visible to the caller
    ("Project Management") -- a Private project is only visible to its
    own members, matching this project's own ``visibility`` field
    rather than treating every project as a platform-wide directory
    entry (the tenant-isolation gap
    ``services/organization-service``'s own live smoke testing caught
    and fixed for its organization-scoped sub-resources).
    """
    records = await projects.list_for_org(organization_id)
    member_project_ids = await members.project_ids_for_user(caller)
    visible = [
        p
        for p in records
        if p.visibility != ProjectVisibility.PRIVATE or p.id in member_project_ids
    ]
    return SuccessResponse(
        message="Projects retrieved.", data=[project_to_response(p) for p in visible], meta=_meta()
    )


@router.get("/{project_id}", response_model=SuccessResponse[ProjectResponse])
async def get_project(
    project_id: UUID, projects: ProjSvc, members: MemberSvc, caller: CurrentUserId
) -> SuccessResponse[ProjectResponse]:
    """Return one project.

    Raises:
        AuthorizationError: If the project is Private and the caller is
            not one of its members.
    """
    project = await projects.get_by_id(project_id)
    if project.visibility == ProjectVisibility.PRIVATE and not await members.is_member(
        project_id, caller
    ):
        raise AuthorizationError("This project is private.")
    return SuccessResponse(
        message="Project retrieved.", data=project_to_response(project), meta=_meta()
    )


@router.post("", response_model=SuccessResponse[ProjectResponse], status_code=201)
async def create_project(
    body: ProjectCreateRequest, projects: ProjSvc, members: MemberSvc, caller: CurrentUserId
) -> SuccessResponse[ProjectResponse]:
    """Create a new project ("Create"). The caller becomes its Owner."""
    project = await projects.create(
        organization_id=body.organization_id,
        owner_id=caller,
        name=body.name,
        code=body.code,
        display_name=body.display_name,
        description=body.description,
        visibility=body.visibility,
        default_language=body.default_language,
        timezone=body.timezone,
        category=body.category,
        priority=body.priority,
        metadata=body.metadata,
    )
    await members.add(
        project.id, caller, organization_id=project.organization_id, role_id=OWNER_ROLE_ID
    )
    return SuccessResponse(
        message="Project created.", data=project_to_response(project), meta=_meta()
    )


@router.put(
    "/{project_id}", response_model=SuccessResponse[ProjectResponse], dependencies=[_RequireAdmin]
)
async def update_project(
    project_id: UUID, body: ProjectUpdateRequest, projects: ProjSvc
) -> SuccessResponse[ProjectResponse]:
    """Replace a project's mutable fields ("Update")."""
    project = await projects.update(
        project_id,
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        status=body.status,
        visibility=body.visibility,
        default_language=body.default_language,
        timezone=body.timezone,
        category=body.category,
        priority=body.priority,
        metadata=body.metadata,
    )
    return SuccessResponse(
        message="Project updated.", data=project_to_response(project), meta=_meta()
    )


@router.patch(
    "/{project_id}", response_model=SuccessResponse[ProjectResponse], dependencies=[_RequireAdmin]
)
async def patch_project(
    project_id: UUID, body: ProjectPatchRequest, projects: ProjSvc
) -> SuccessResponse[ProjectResponse]:
    """Update only the given fields of a project ("PATCH partial update")."""
    project = await projects.patch(
        project_id,
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        status=body.status,
        visibility=body.visibility,
        default_language=body.default_language,
        timezone=body.timezone,
        category=body.category,
        priority=body.priority,
        metadata=body.metadata,
    )
    return SuccessResponse(
        message="Project updated.", data=project_to_response(project), meta=_meta()
    )


@router.delete(
    "/{project_id}", response_model=SuccessResponse[dict[str, bool]], dependencies=[_RequireAdmin]
)
async def delete_project(project_id: UUID, projects: ProjSvc) -> SuccessResponse[dict[str, bool]]:
    """Soft-delete a project ("Soft Delete")."""
    await projects.delete(project_id)
    return SuccessResponse(message="Project deleted.", data={"success": True}, meta=_meta())


@router.post(
    "/{project_id}/clone",
    response_model=SuccessResponse[ProjectResponse],
    status_code=201,
    dependencies=[_RequireAdmin],
)
async def clone_project(
    project_id: UUID,
    body: ProjectCloneRequest,
    projects: ProjSvc,
    members: MemberSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ProjectResponse]:
    """Clone a project into a brand-new one ("Clone"). The caller becomes
    the clone's Owner.
    """
    clone = await projects.clone(project_id, name=body.name, code=body.code, cloned_by=caller)
    await members.add(
        clone.id, caller, organization_id=clone.organization_id, role_id=OWNER_ROLE_ID
    )
    return SuccessResponse(message="Project cloned.", data=project_to_response(clone), meta=_meta())


@router.post(
    "/{project_id}/archive",
    response_model=SuccessResponse[ProjectResponse],
    dependencies=[_RequireAdmin],
)
async def archive_project(
    project_id: UUID, body: ProjectArchiveRequest, projects: ProjSvc, caller: CurrentUserId
) -> SuccessResponse[ProjectResponse]:
    """Archive a project ("Archive")."""
    project = await projects.archive(project_id, archived_by=caller, reason=body.reason)
    return SuccessResponse(
        message="Project archived.", data=project_to_response(project), meta=_meta()
    )


@router.post(
    "/{project_id}/restore",
    response_model=SuccessResponse[ProjectResponse],
    dependencies=[_RequireAdmin],
)
async def restore_project(
    project_id: UUID, projects: ProjSvc, caller: CurrentUserId
) -> SuccessResponse[ProjectResponse]:
    """Restore an archived project ("Restore")."""
    project = await projects.restore(project_id, restored_by=caller)
    return SuccessResponse(
        message="Project restored.", data=project_to_response(project), meta=_meta()
    )


__all__ = ["project_to_response", "router"]
