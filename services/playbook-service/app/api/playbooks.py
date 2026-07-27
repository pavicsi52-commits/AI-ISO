"""``/playbooks`` and its ``versions``/``approve``/``publish``/
``import``/``export`` actions. Per docs/041 REST list.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import (
    ApprovalSvc,
    CurrentUserId,
    LabelSvc,
    PlaybookSvc,
    TagSvc,
    VersionSvc,
)
from app.models.enums import ApprovalStatus, PlaybookStatus
from app.models.playbook import Playbook
from app.models.playbook_approval import PlaybookApproval
from app.models.playbook_version import PlaybookVersion
from app.schemas.approval import PlaybookApprovalCreateRequest, PlaybookApprovalResponse
from app.schemas.playbook import (
    PlaybookCreateRequest,
    PlaybookExportResponse,
    PlaybookImportRequest,
    PlaybookResponse,
    PlaybookUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.version import PlaybookVersionResponse

router = APIRouter(prefix="/playbooks", tags=["Playbooks"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def playbook_to_response(playbook: Playbook) -> PlaybookResponse:
    return PlaybookResponse(
        id=playbook.id,
        organization_id=playbook.organization_id,
        project_id=playbook.project_id,
        name=playbook.name,
        display_name=playbook.display_name,
        description=playbook.description,
        content_type=playbook.content_type,
        status=playbook.status,
        current_version=playbook.current_version,
        category_id=playbook.category_id,
        repository_id=playbook.repository_id,
        owner_id=playbook.owner_id,
        author_id=playbook.author_id,
        entry_file=playbook.entry_file,
        metadata=playbook.metadata_,
    )


def version_to_response(version: PlaybookVersion) -> PlaybookVersionResponse:
    return PlaybookVersionResponse(
        id=version.id,
        playbook_id=version.playbook_id,
        version_number=version.version_number,
        content=version.content,
        checksum=version.checksum,
        release_notes=version.release_notes,
        change_summary=version.change_summary,
        changed_by=version.changed_by,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
        created_at=version.created_at,
    )


def approval_to_response(approval: PlaybookApproval) -> PlaybookApprovalResponse:
    return PlaybookApprovalResponse(
        id=approval.id,
        playbook_id=approval.playbook_id,
        version_id=approval.version_id,
        approval_type=approval.approval_type,
        status=approval.status,
        level=approval.level,
        requested_by=approval.requested_by,
        approver_id=approval.approver_id,
        comments=approval.comments,
        decided_at=approval.decided_at,
    )


@router.get("", response_model=SuccessResponse[list[PlaybookResponse]])
async def list_playbooks(
    organization_id: UUID,
    playbooks: PlaybookSvc,
    _caller: CurrentUserId,
    status: PlaybookStatus | None = None,
) -> SuccessResponse[list[PlaybookResponse]]:
    """List every playbook in *organization_id*."""
    records = await playbooks.list_for_org(organization_id, status=status)
    data = [playbook_to_response(record) for record in records]
    return SuccessResponse(message="Playbooks retrieved.", data=data, meta=_meta())


@router.get("/{playbook_id}", response_model=SuccessResponse[PlaybookResponse])
async def get_playbook(
    playbook_id: UUID, playbooks: PlaybookSvc, _caller: CurrentUserId
) -> SuccessResponse[PlaybookResponse]:
    """Return one playbook.

    Raises:
        NotFoundError: If no such playbook exists.
    """
    playbook = await playbooks.get_by_id(playbook_id)
    return SuccessResponse(
        message="Playbook retrieved.", data=playbook_to_response(playbook), meta=_meta()
    )


@router.post("", response_model=SuccessResponse[PlaybookResponse], status_code=201)
async def create_playbook(
    body: PlaybookCreateRequest, playbooks: PlaybookSvc, caller: CurrentUserId
) -> SuccessResponse[PlaybookResponse]:
    """Define a new playbook and its own first content version ("Create")."""
    playbook = await playbooks.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        content_type=body.content_type,
        category_id=body.category_id,
        repository_id=body.repository_id,
        owner_id=body.owner_id,
        author_id=body.author_id,
        entry_file=body.entry_file,
        metadata=body.metadata,
        initial_content=body.initial_content,
        created_by=caller,
    )
    return SuccessResponse(
        message="Playbook created.", data=playbook_to_response(playbook), meta=_meta()
    )


@router.put("/{playbook_id}", response_model=SuccessResponse[PlaybookResponse])
async def update_playbook(
    playbook_id: UUID, body: PlaybookUpdateRequest, playbooks: PlaybookSvc, caller: CurrentUserId
) -> SuccessResponse[PlaybookResponse]:
    """Replace a playbook's mutable fields ("Update")."""
    playbook = await playbooks.update(
        playbook_id,
        actor_id=caller,
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        status=body.status,
        category_id=body.category_id,
        repository_id=body.repository_id,
        owner_id=body.owner_id,
        author_id=body.author_id,
        entry_file=body.entry_file,
        metadata=body.metadata,
    )
    return SuccessResponse(
        message="Playbook updated.", data=playbook_to_response(playbook), meta=_meta()
    )


@router.delete("/{playbook_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_playbook(
    playbook_id: UUID, playbooks: PlaybookSvc, caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Soft-delete a playbook ("Delete")."""
    await playbooks.delete(playbook_id, actor_id=caller)
    return SuccessResponse(message="Playbook deleted.", data={"success": True}, meta=_meta())


@router.get(
    "/{playbook_id}/versions", response_model=SuccessResponse[list[PlaybookVersionResponse]]
)
async def list_playbook_versions(
    playbook_id: UUID, versions: VersionSvc, _caller: CurrentUserId
) -> SuccessResponse[list[PlaybookVersionResponse]]:
    """List every version recorded for a playbook ("Version History")."""
    records = await versions.list_for_playbook(playbook_id)
    data = [version_to_response(record) for record in records]
    return SuccessResponse(message="Playbook versions retrieved.", data=data, meta=_meta())


@router.post(
    "/{playbook_id}/approve",
    response_model=SuccessResponse[PlaybookApprovalResponse],
    status_code=201,
)
async def approve_playbook(
    playbook_id: UUID,
    body: PlaybookApprovalCreateRequest,
    approvals: ApprovalSvc,
    caller: CurrentUserId,
) -> SuccessResponse[PlaybookApprovalResponse]:
    """Request and immediately record an approval decision for a playbook."""
    approval = await approvals.request(
        playbook_id,
        version_id=body.version_id,
        approval_type=body.approval_type,
        level=body.level,
        requested_by=body.requested_by or caller,
    )
    approval = await approvals.decide(
        approval.id, status=ApprovalStatus.APPROVED, approver_id=caller, comments=body.comments
    )
    return SuccessResponse(
        message="Playbook approved.", data=approval_to_response(approval), meta=_meta()
    )


@router.post("/{playbook_id}/publish", response_model=SuccessResponse[PlaybookResponse])
async def publish_playbook(
    playbook_id: UUID, playbooks: PlaybookSvc, caller: CurrentUserId
) -> SuccessResponse[PlaybookResponse]:
    """Publish a playbook ("Publishing Approval" / status transition)."""
    playbook = await playbooks.set_status(
        playbook_id, status=PlaybookStatus.PUBLISHED, actor_id=caller
    )
    return SuccessResponse(
        message="Playbook published.", data=playbook_to_response(playbook), meta=_meta()
    )


@router.post("/import", response_model=SuccessResponse[PlaybookResponse], status_code=201)
async def import_playbook(
    body: PlaybookImportRequest,
    playbooks: PlaybookSvc,
    tags: TagSvc,
    labels: LabelSvc,
    caller: CurrentUserId,
) -> SuccessResponse[PlaybookResponse]:
    """Import a complete playbook definition, including its own tags
    and labels ("Import").
    """
    created = body.playbook
    playbook = await playbooks.create(
        organization_id=created.organization_id,
        project_id=created.project_id,
        name=created.name,
        display_name=created.display_name,
        description=created.description,
        content_type=created.content_type,
        category_id=created.category_id,
        repository_id=created.repository_id,
        owner_id=created.owner_id,
        author_id=created.author_id,
        entry_file=created.entry_file,
        metadata=created.metadata,
        initial_content=created.initial_content,
        created_by=caller,
    )
    for tag in body.tags:
        await tags.add(playbook.id, tag=tag)
    for key, value in body.labels.items():
        await labels.add(playbook.id, key=key, value=value)
    return SuccessResponse(
        message="Playbook imported.", data=playbook_to_response(playbook), meta=_meta()
    )


@router.post("/export", response_model=SuccessResponse[PlaybookExportResponse])
async def export_playbook(
    playbook_id: UUID,
    playbooks: PlaybookSvc,
    versions: VersionSvc,
    tags: TagSvc,
    labels: LabelSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[PlaybookExportResponse]:
    """Export a complete playbook definition, including its own latest
    content, tags, and labels ("Export").

    Raises:
        NotFoundError: If *playbook_id* does not exist, or has no content yet.
    """
    playbook = await playbooks.get_by_id(playbook_id)
    latest = await versions.get_latest_for_playbook(playbook_id)
    content = latest.content if latest is not None else ""
    tag_records = await tags.list_for_playbook(playbook_id)
    label_records = await labels.list_for_playbook(playbook_id)
    bundle = PlaybookExportResponse(
        playbook=playbook_to_response(playbook),
        content=content,
        tags=[record.tag for record in tag_records],
        labels={record.key: record.value for record in label_records},
    )
    return SuccessResponse(message="Playbook exported.", data=bundle, meta=_meta())


__all__ = [
    "approval_to_response",
    "playbook_to_response",
    "router",
    "version_to_response",
]
