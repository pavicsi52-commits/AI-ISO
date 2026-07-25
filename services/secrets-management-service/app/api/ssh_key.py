"""``/ssh-keys``. Per docs/035 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, SSHKeySvc
from app.models.ssh_key import SSHKey
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.ssh_key import SSHKeyCreateRequest, SSHKeyCreateResponse, SSHKeyResponse

router = APIRouter(prefix="/ssh-keys", tags=["SSH Keys"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(ssh_key: SSHKey) -> SSHKeyResponse:
    return SSHKeyResponse(
        id=ssh_key.id,
        organization_id=ssh_key.organization_id,
        project_id=ssh_key.project_id,
        name=ssh_key.name,
        key_type=ssh_key.key_type,
        public_key=ssh_key.public_key,
        private_key_secret_id=ssh_key.private_key_secret_id,
        fingerprint=ssh_key.fingerprint,
        status=ssh_key.status,
        expires_at=ssh_key.expires_at,
        created_at=ssh_key.created_at,
        updated_at=ssh_key.updated_at,
    )


@router.get("", response_model=SuccessResponse[list[SSHKeyResponse]])
async def list_ssh_keys(
    organization_id: UUID, ssh_keys: SSHKeySvc, _caller: CurrentUserId
) -> SuccessResponse[list[SSHKeyResponse]]:
    """List every SSH key belonging to *organization_id* -- never private keys."""
    records = await ssh_keys.list_for_org(organization_id)
    return SuccessResponse(
        message="SSH keys retrieved.", data=[_to_response(k) for k in records], meta=_meta()
    )


@router.post("", response_model=SuccessResponse[SSHKeyCreateResponse], status_code=201)
async def create_ssh_key(
    body: SSHKeyCreateRequest, ssh_keys: SSHKeySvc, _caller: CurrentUserId
) -> SuccessResponse[SSHKeyCreateResponse]:
    """Generate a fresh SSH keypair, or import an existing one ("Key
    Generation"/"Import").
    """
    ssh_key, private_key = await ssh_keys.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        key_type=body.key_type,
        owner_id=body.owner_id,
        expires_at=body.expires_at,
        public_key=body.public_key,
        private_key=body.private_key,
    )
    data = SSHKeyCreateResponse(**_to_response(ssh_key).model_dump(), private_key=private_key)
    return SuccessResponse(message="SSH key created.", data=data, meta=_meta())


@router.delete("/{ssh_key_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_ssh_key(
    ssh_key_id: UUID, ssh_keys: SSHKeySvc, _caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Delete an SSH key."""
    await ssh_keys.delete(ssh_key_id)
    return SuccessResponse(message="SSH key deleted.", data={"success": True}, meta=_meta())


__all__ = ["router"]
