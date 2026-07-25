"""``/providers``. Per docs/035 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, ProviderSvc
from app.models.secret_provider import SecretProvider
from app.schemas.provider import ProviderCreateRequest, ProviderResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/providers", tags=["Providers"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(provider: SecretProvider) -> ProviderResponse:
    return ProviderResponse(
        id=provider.id,
        organization_id=provider.organization_id,
        name=provider.name,
        provider_type=provider.provider_type,
        config=provider.config,
        connection_secret_id=provider.connection_secret_id,
        is_enabled=provider.is_enabled,
    )


@router.get("", response_model=SuccessResponse[list[ProviderResponse]])
async def list_providers(
    organization_id: UUID, providers: ProviderSvc, _caller: CurrentUserId
) -> SuccessResponse[list[ProviderResponse]]:
    """List every provider configured for *organization_id* ("Provider
    Abstraction Layer").
    """
    records = await providers.list_for_org(organization_id)
    return SuccessResponse(
        message="Providers retrieved.", data=[_to_response(p) for p in records], meta=_meta()
    )


@router.post("", response_model=SuccessResponse[ProviderResponse], status_code=201)
async def create_provider(
    body: ProviderCreateRequest, providers: ProviderSvc, _caller: CurrentUserId
) -> SuccessResponse[ProviderResponse]:
    """Register a new provider configuration."""
    provider = await providers.create(
        organization_id=body.organization_id,
        name=body.name,
        provider_type=body.provider_type,
        config=body.config,
        connection_secret_id=body.connection_secret_id,
        is_enabled=body.is_enabled,
    )
    return SuccessResponse(
        message="Provider registered.", data=_to_response(provider), meta=_meta()
    )


__all__ = ["router"]
