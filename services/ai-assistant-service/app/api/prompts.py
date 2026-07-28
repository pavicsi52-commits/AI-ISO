"""``/ai/prompts`` -- template management with versioning and approval.

Added beyond docs/046's own literal REST list: "Prompt Management" is
an explicit ACCEPTANCE CRITERIA line naming Versioning, Approval, and
Rollback, none of which is reachable without these endpoints.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, PromptSvc
from app.models.ai_prompt import AiPrompt
from app.models.ai_prompt_version import AiPromptVersion
from app.models.enums import AuditOutcome
from app.schemas.prompt import (
    PromptCreateRequest,
    PromptRenderRequest,
    PromptRenderResponse,
    PromptResponse,
    PromptVersionCreateRequest,
    PromptVersionResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/ai/prompts", tags=["AI Prompts"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def prompt_to_response(prompt: AiPrompt) -> PromptResponse:
    """Map a prompt row onto its own response schema."""
    return PromptResponse(
        id=prompt.id,
        organization_id=prompt.organization_id,
        project_id=prompt.project_id,
        name=prompt.name,
        description=prompt.description,
        current_version_number=prompt.current_version_number,
        enabled=prompt.enabled,
    )


def version_to_response(version: AiPromptVersion) -> PromptVersionResponse:
    """Map a prompt version row onto its own response schema."""
    return PromptVersionResponse(
        id=version.id,
        prompt_id=version.prompt_id,
        version_number=version.version_number,
        template=version.template,
        variables=version.variables,
        status=version.status,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
    )


@router.get("", response_model=SuccessResponse[list[PromptResponse]])
async def list_prompts(
    organization_id: UUID, prompts: PromptSvc, _caller: CurrentUserId
) -> SuccessResponse[list[PromptResponse]]:
    """Every prompt registered for an organization."""
    records = await prompts.list_for_org(organization_id)
    return SuccessResponse(
        message="Prompts retrieved.",
        data=[prompt_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post("", response_model=SuccessResponse[PromptResponse], status_code=201)
async def create_prompt(
    body: PromptCreateRequest, prompts: PromptSvc, caller: CurrentUserId, audit: AuditSvc
) -> SuccessResponse[PromptResponse]:
    """Create a prompt with its own first draft version."""
    prompt, _version = await prompts.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        template=body.template,
        variables=body.variables,
    )
    await audit.record(
        organization_id=body.organization_id,
        actor_id=caller,
        action="prompt.created",
        entity_type="AiPrompt",
        entity_id=prompt.id,
        outcome=AuditOutcome.SUCCESS,
        reason=f"Prompt {body.name!r} created.",
    )
    return SuccessResponse(message="Prompt created.", data=prompt_to_response(prompt), meta=_meta())


@router.get("/{prompt_id}/versions", response_model=SuccessResponse[list[PromptVersionResponse]])
async def list_prompt_versions(
    prompt_id: UUID, prompts: PromptSvc, _caller: CurrentUserId
) -> SuccessResponse[list[PromptVersionResponse]]:
    """Every revision of a prompt."""
    records = await prompts.list_versions(prompt_id)
    return SuccessResponse(
        message="Prompt versions retrieved.",
        data=[version_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post(
    "/{prompt_id}/versions", response_model=SuccessResponse[PromptVersionResponse], status_code=201
)
async def add_prompt_version(
    prompt_id: UUID,
    body: PromptVersionCreateRequest,
    prompts: PromptSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[PromptVersionResponse]:
    """Add a new draft revision.

    Raises:
        NotFoundError: If no such prompt exists.
    """
    version = await prompts.add_version(prompt_id, template=body.template, variables=body.variables)
    return SuccessResponse(
        message="Prompt version created.", data=version_to_response(version), meta=_meta()
    )


@router.post(
    "/{prompt_id}/versions/{version_number}/approve",
    response_model=SuccessResponse[PromptVersionResponse],
)
async def approve_prompt_version(
    prompt_id: UUID,
    version_number: str,
    prompts: PromptSvc,
    caller: CurrentUserId,
    audit: AuditSvc,
) -> SuccessResponse[PromptVersionResponse]:
    """Approve a revision and make it current.

    Raises:
        NotFoundError: If no such prompt or revision exists.
        ConflictError: If the revision is archived.
    """
    version = await prompts.approve(prompt_id, version_number, approved_by=caller)
    prompt = await prompts.get_by_id(prompt_id)
    await audit.record(
        organization_id=prompt.organization_id,
        actor_id=caller,
        action="prompt.approved",
        entity_type="AiPromptVersion",
        entity_id=version.id,
        outcome=AuditOutcome.SUCCESS,
        reason=f"Version {version_number!r} approved.",
    )
    return SuccessResponse(
        message="Prompt version approved.", data=version_to_response(version), meta=_meta()
    )


@router.post(
    "/{prompt_id}/rollback/{version_number}", response_model=SuccessResponse[PromptResponse]
)
async def rollback_prompt(
    prompt_id: UUID,
    version_number: str,
    prompts: PromptSvc,
    caller: CurrentUserId,
    audit: AuditSvc,
) -> SuccessResponse[PromptResponse]:
    """Roll a prompt back onto an earlier approved revision.

    Raises:
        NotFoundError: If no such prompt or revision exists.
        ConflictError: If that revision was never approved.
    """
    prompt = await prompts.rollback(prompt_id, version_number)
    await audit.record(
        organization_id=prompt.organization_id,
        actor_id=caller,
        action="prompt.rolled_back",
        entity_type="AiPrompt",
        entity_id=prompt.id,
        outcome=AuditOutcome.SUCCESS,
        reason=f"Rolled back to {version_number!r}.",
    )
    return SuccessResponse(
        message="Prompt rolled back.", data=prompt_to_response(prompt), meta=_meta()
    )


@router.post("/{prompt_id}/render", response_model=SuccessResponse[PromptRenderResponse])
async def render_prompt(
    prompt_id: UUID,
    body: PromptRenderRequest,
    prompts: PromptSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[PromptRenderResponse]:
    """Render a prompt's own current approved version.

    Raises:
        NotFoundError: If the prompt or its current version is missing.
        ConflictError: If the current version is not approved.
        ValidationError: If a declared variable was not supplied.
    """
    rendered = await prompts.render(prompt_id, dict(body.variables))
    prompt = await prompts.get_by_id(prompt_id)
    if prompt is None:  # pragma: no cover - require_by_id already raises
        raise NotFoundError(f"Prompt {prompt_id!r} not found.")
    return SuccessResponse(
        message="Prompt rendered.",
        data=PromptRenderResponse(
            prompt_id=prompt_id,
            version_number=prompt.current_version_number,
            rendered=rendered,
        ),
        meta=_meta(),
    )


__all__ = ["prompt_to_response", "router", "version_to_response"]
