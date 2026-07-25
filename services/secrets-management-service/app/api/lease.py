"""``DELETE /leases/{id}``. Per docs/035 REST list and "SECRET LEASING":
Revoke Lease.

Issuing a lease is ``POST /secrets/{id}/lease``, handled by
``app/api/secret.py`` (a lease is created *from* a secret); revoking one
only needs the lease's own id, so it gets its own top-level
``/leases`` prefix instead.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, LeaseSvc, SecretSvc
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/leases", tags=["Secrets"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.delete("/{lease_id}", response_model=SuccessResponse[dict[str, bool]])
async def revoke_lease(
    lease_id: UUID, leases: LeaseSvc, secrets: SecretSvc, caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Revoke a lease ("Revoke Lease").

    Raises:
        AuthorizationError: If the caller is neither the lease's own
            principal nor the underlying secret's owner.
    """
    lease = await leases.get_by_id(lease_id)
    if lease.principal_id != caller:
        secret = await secrets.get_by_id(lease.secret_id)
        if secret.owner_id != caller:
            raise AuthorizationError("You may not revoke this lease.")
    await leases.revoke(lease_id)
    return SuccessResponse(message="Lease revoked.", data={"success": True}, meta=_meta())


__all__ = ["router"]
