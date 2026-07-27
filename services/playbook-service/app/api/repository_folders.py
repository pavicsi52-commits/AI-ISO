"""``GET /playbooks/repository``. Per docs/041 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, RepositoryFolderSvc
from app.models.playbook_repository import PlaybookRepositoryFolder
from app.schemas.repository_folder import PlaybookRepositoryFolderResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/playbooks/repository", tags=["Repository"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def folder_to_response(folder: PlaybookRepositoryFolder) -> PlaybookRepositoryFolderResponse:
    return PlaybookRepositoryFolderResponse(
        id=folder.id,
        organization_id=folder.organization_id,
        name=folder.name,
        description=folder.description,
        repository_type=folder.repository_type,
        visibility=folder.visibility,
    )


@router.get("", response_model=SuccessResponse[list[PlaybookRepositoryFolderResponse]])
async def list_repository_folders(
    organization_id: UUID, folders: RepositoryFolderSvc, _caller: CurrentUserId
) -> SuccessResponse[list[PlaybookRepositoryFolderResponse]]:
    """List every playbook repository folder in *organization_id* ("Folder Organization")."""
    records = await folders.list_for_org(organization_id)
    data = [folder_to_response(record) for record in records]
    return SuccessResponse(
        message="Playbook repository folders retrieved.", data=data, meta=_meta()
    )


__all__ = ["folder_to_response", "router"]
