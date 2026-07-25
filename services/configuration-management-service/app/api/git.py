"""``GET/POST /configurations/git``. Per docs/039 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, GitOpsSvc
from app.models.configuration_git_repository import ConfigurationGitRepository
from app.schemas.git import (
    ConfigurationGitRepositoryCreateRequest,
    ConfigurationGitRepositoryResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/configurations", tags=["GitOps"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def git_repository_to_response(
    repository: ConfigurationGitRepository,
) -> ConfigurationGitRepositoryResponse:
    return ConfigurationGitRepositoryResponse(
        id=repository.id,
        organization_id=repository.organization_id,
        project_id=repository.project_id,
        profile_id=repository.profile_id,
        provider=repository.provider,
        repository_url=repository.repository_url,
        branch=repository.branch,
        sync_status=repository.sync_status,
        last_synced_at=repository.last_synced_at,
    )


@router.get("/git", response_model=SuccessResponse[list[ConfigurationGitRepositoryResponse]])
async def list_git_repositories(
    organization_id: UUID, gitops: GitOpsSvc, _caller: CurrentUserId
) -> SuccessResponse[list[ConfigurationGitRepositoryResponse]]:
    """List every Git repository registered for *organization_id*."""
    records = await gitops.list_for_org(organization_id)
    data = [git_repository_to_response(record) for record in records]
    return SuccessResponse(message="Git repositories retrieved.", data=data, meta=_meta())


@router.post(
    "/git", response_model=SuccessResponse[ConfigurationGitRepositoryResponse], status_code=201
)
async def register_git_repository(
    body: ConfigurationGitRepositoryCreateRequest, gitops: GitOpsSvc, _caller: CurrentUserId
) -> SuccessResponse[ConfigurationGitRepositoryResponse]:
    """Register a Git repository to back a profile's GitOps workflow."""
    repository = await gitops.register(
        organization_id=body.organization_id,
        project_id=body.project_id,
        profile_id=body.profile_id,
        provider=body.provider,
        repository_url=body.repository_url,
        branch=body.branch,
        credential_ref=body.credential_ref,
        webhook_secret_ref=body.webhook_secret_ref,
    )
    return SuccessResponse(
        message="Git repository registered.",
        data=git_repository_to_response(repository),
        meta=_meta(),
    )


__all__ = ["git_repository_to_response", "router"]
