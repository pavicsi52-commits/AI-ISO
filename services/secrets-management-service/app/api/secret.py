"""``/secrets``. Per docs/035 REST list.

``POST /secrets`` requires only authentication -- there is no existing
grant to check for a brand-new secret, the caller automatically becomes
its owner, the same bootstrap shape every AI-IOS tenant-root-adjacent
``POST`` endpoint uses. Every other mutation is gated by
:func:`app.api.deps.require_secret_action`, which allows the secret's
owner unconditionally or anyone holding a matching, non-expired
:class:`~app.models.secret_access.SecretAccessGrant`.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, LeaseSvc, SecretSvc, SecretTagSvc, require_secret_action
from app.models.enums import SecretAccessAction
from app.models.secret import Secret
from app.schemas.lease import SecretLeaseRequest, SecretLeaseResponse
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.secret import (
    SecretCreateRequest,
    SecretDetailResponse,
    SecretRotateRequest,
    SecretSummaryResponse,
    SecretUpdateRequest,
)

router = APIRouter(prefix="/secrets", tags=["Secrets"])

_RequireRead = Depends(require_secret_action(SecretAccessAction.READ))
_RequireWrite = Depends(require_secret_action(SecretAccessAction.WRITE))
_RequireDelete = Depends(require_secret_action(SecretAccessAction.DELETE))
_RequireRotate = Depends(require_secret_action(SecretAccessAction.ROTATE))
_RequireLease = Depends(require_secret_action(SecretAccessAction.LEASE))


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def secret_to_summary(secret: Secret, *, tags: list[str] | None = None) -> SecretSummaryResponse:
    return SecretSummaryResponse(
        id=secret.id,
        organization_id=secret.organization_id,
        project_id=secret.project_id,
        name=secret.name,
        description=secret.description,
        category_id=secret.category_id,
        secret_type=secret.secret_type,
        status=secret.status,
        owner_id=secret.owner_id,
        current_version=secret.current_version,
        expires_at=secret.expires_at,
        rotation_policy=secret.rotation_policy,
        metadata=secret.metadata_,
        tags=tags or [],
        created_at=secret.created_at,
        updated_at=secret.updated_at,
    )


@router.get("", response_model=SuccessResponse[list[SecretSummaryResponse]])
async def list_secrets(
    organization_id: UUID, secrets: SecretSvc, _caller: CurrentUserId
) -> SuccessResponse[list[SecretSummaryResponse]]:
    """List every secret in *organization_id* -- metadata only, never
    values ("SECRET SEARCH"). Omits tags to avoid an N+1 lookup per
    secret; fetch a single secret via ``GET /secrets/{id}`` for its tags.

    Requires authentication but, unlike ``GET /secrets/{id}``, does not
    filter by per-secret access grants -- a lower bar is defensible here
    since list/search responses never carry a decrypted value, matching
    how e.g. HashiCorp Vault lets any authenticated caller list secret
    *paths* within their scope while still gating individual reads.
    """
    records = await secrets.list_for_org(organization_id)
    return SuccessResponse(
        message="Secrets retrieved.",
        data=[secret_to_summary(s) for s in records],
        meta=_meta(),
    )


@router.get(
    "/{secret_id}",
    response_model=SuccessResponse[SecretDetailResponse],
    dependencies=[_RequireRead],
)
async def get_secret(
    secret_id: UUID, secrets: SecretSvc, tags: SecretTagSvc, caller: CurrentUserId
) -> SuccessResponse[SecretDetailResponse]:
    """Return one secret, including its decrypted current value ("Read"/
    "Decrypt") -- see ``app/schemas/secret.py``'s module docstring for
    why this is the one response shape that carries plaintext.
    """
    secret, value = await secrets.get_decrypted(secret_id, actor_id=caller)
    labels = [tag.label for tag in await tags.list_for_secret(secret_id)]
    summary = secret_to_summary(secret, tags=labels)
    data = SecretDetailResponse(**summary.model_dump(), value=value)
    return SuccessResponse(message="Secret retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[SecretSummaryResponse], status_code=201)
async def create_secret(
    body: SecretCreateRequest, secrets: SecretSvc, _caller: CurrentUserId
) -> SuccessResponse[SecretSummaryResponse]:
    """Create a new secret and its initial value version ("Create").

    Requires only authentication -- see the module docstring; *owner_id*
    is an explicit body field rather than always the caller, since an
    admin may provision a secret on behalf of a different principal
    (e.g. a service account).
    """
    secret = await secrets.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        category_id=body.category_id,
        secret_type=body.secret_type,
        owner_id=body.owner_id,
        value=body.value,
        expires_at=body.expires_at,
        rotation_policy=body.rotation_policy,
        metadata=body.metadata,
        tags=body.tags,
    )
    return SuccessResponse(
        message="Secret created.", data=secret_to_summary(secret, tags=body.tags), meta=_meta()
    )


@router.put(
    "/{secret_id}",
    response_model=SuccessResponse[SecretSummaryResponse],
    dependencies=[_RequireWrite],
)
async def update_secret(
    secret_id: UUID,
    body: SecretUpdateRequest,
    secrets: SecretSvc,
    tags: SecretTagSvc,
    caller: CurrentUserId,
) -> SuccessResponse[SecretSummaryResponse]:
    """Update a secret's identity/lifecycle fields -- never its value
    ("Update").
    """
    secret = await secrets.update(
        secret_id,
        actor_id=caller,
        name=body.name,
        description=body.description,
        category_id=body.category_id,
        status=body.status,
        expires_at=body.expires_at,
        rotation_policy=body.rotation_policy,
        metadata=body.metadata,
    )
    labels = [tag.label for tag in await tags.list_for_secret(secret_id)]
    return SuccessResponse(
        message="Secret updated.", data=secret_to_summary(secret, tags=labels), meta=_meta()
    )


@router.delete(
    "/{secret_id}", response_model=SuccessResponse[dict[str, bool]], dependencies=[_RequireDelete]
)
async def delete_secret(
    secret_id: UUID, secrets: SecretSvc, caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Soft-delete a secret ("Soft Delete")."""
    await secrets.delete(secret_id, actor_id=caller)
    return SuccessResponse(message="Secret deleted.", data={"success": True}, meta=_meta())


@router.post(
    "/{secret_id}/rotate",
    response_model=SuccessResponse[SecretSummaryResponse],
    dependencies=[_RequireRotate],
)
async def rotate_secret(
    secret_id: UUID,
    body: SecretRotateRequest,
    secrets: SecretSvc,
    tags: SecretTagSvc,
    caller: CurrentUserId,
) -> SuccessResponse[SecretSummaryResponse]:
    """Rotate a secret's value ("Manual Rotation")."""
    secret = await secrets.rotate(secret_id, new_value=body.new_value, rotated_by=caller)
    labels = [tag.label for tag in await tags.list_for_secret(secret_id)]
    return SuccessResponse(
        message="Secret rotated.", data=secret_to_summary(secret, tags=labels), meta=_meta()
    )


@router.post(
    "/{secret_id}/lease",
    response_model=SuccessResponse[SecretLeaseResponse],
    status_code=201,
    dependencies=[_RequireLease],
)
async def lease_secret(
    secret_id: UUID, body: SecretLeaseRequest, secrets: SecretSvc, leases: LeaseSvc
) -> SuccessResponse[SecretLeaseResponse]:
    """Issue a temporary-credential lease on a secret's current value
    ("Temporary Credentials").
    """
    secret = await secrets.get_by_id(secret_id)
    lease, value = await leases.issue(
        secret_id,
        organization_id=secret.organization_id,
        principal_id=body.principal_id,
        duration_seconds=body.duration_seconds,
    )
    data = SecretLeaseResponse(
        id=lease.id,
        secret_id=lease.secret_id,
        principal_id=lease.principal_id,
        status=lease.status,
        value=value,
        issued_at=lease.issued_at,
        expires_at=lease.expires_at,
        lease_duration_seconds=lease.lease_duration_seconds,
        renewed_count=lease.renewed_count,
    )
    return SuccessResponse(message="Lease issued.", data=data, meta=_meta())


__all__ = ["router", "secret_to_summary"]
