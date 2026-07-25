"""``/assets/{id}/contracts``. Per docs/038 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import ContractSvc, CurrentUserId
from app.models.asset_contract import AssetContract
from app.schemas.contract import AssetContractCreateRequest, AssetContractResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/assets", tags=["Contracts"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def contract_to_response(contract: AssetContract) -> AssetContractResponse:
    return AssetContractResponse(
        id=contract.id,
        managed_asset_id=contract.managed_asset_id,
        vendor_id=contract.vendor_id,
        contract_type=contract.contract_type,
        status=contract.status,
        contract_number=contract.contract_number,
        start_date=contract.start_date,
        end_date=contract.end_date,
        renewal_status=contract.renewal_status,
        documents=contract.documents,
    )


@router.get(
    "/{managed_asset_id}/contracts", response_model=SuccessResponse[list[AssetContractResponse]]
)
async def list_contracts(
    managed_asset_id: UUID, contracts: ContractSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AssetContractResponse]]:
    """List every contract covering a managed asset."""
    records = await contracts.list_for_managed_asset(managed_asset_id)
    data = [contract_to_response(record) for record in records]
    return SuccessResponse(message="Contracts retrieved.", data=data, meta=_meta())


@router.post(
    "/{managed_asset_id}/contracts",
    response_model=SuccessResponse[AssetContractResponse],
    status_code=201,
)
async def create_contract(
    managed_asset_id: UUID,
    body: AssetContractCreateRequest,
    contracts: ContractSvc,
    _caller: CurrentUserId,
    organization_id: UUID,
) -> SuccessResponse[AssetContractResponse]:
    """Add a contract covering a managed asset ("Support Contracts"/etc.)."""
    record = await contracts.create(
        managed_asset_id,
        organization_id=organization_id,
        vendor_id=body.vendor_id,
        contract_type=body.contract_type,
        contract_number=body.contract_number,
        start_date=body.start_date,
        end_date=body.end_date,
        documents=body.documents,
    )
    return SuccessResponse(
        message="Contract created.", data=contract_to_response(record), meta=_meta()
    )


__all__ = ["contract_to_response", "router"]
