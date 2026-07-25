"""Construction tests for the response schemas backing internal
services that have no dedicated top-level REST endpoint of their own
(owners/contacts, firmware, software, procurement/depreciation,
lifecycle, audit) -- see each service's own docstring for why.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.enums import (
    AuditOutcome,
    ComplianceStatus,
    DepreciationMethod,
    LifecycleState,
    SoftwareEndOfLifeStatus,
)
from app.schemas.audit import AssetAuditResponse
from app.schemas.firmware import AssetFirmwareResponse
from app.schemas.lifecycle import (
    AssetChangeHistoryResponse,
    AssetRetirementResponse,
    LifecycleActionRequest,
)
from app.schemas.procurement import AssetDepreciationResponse, AssetProcurementResponse
from app.schemas.software import AssetPatchHistoryResponse, AssetSoftwareResponse


def test_audit_response() -> None:
    response = AssetAuditResponse(
        id=uuid.uuid4(),
        managed_asset_id=uuid.uuid4(),
        actor_id=None,
        action="create",
        outcome=AuditOutcome.SUCCESS,
        reason="",
        before=None,
        after={"business_name": "Payments API"},
    )
    assert response.action == "create"


def test_firmware_response() -> None:
    response = AssetFirmwareResponse(
        id=uuid.uuid4(),
        managed_asset_id=uuid.uuid4(),
        current_version="1.0.0",
        available_version=None,
        compliance_status=ComplianceStatus.COMPLIANT,
        vendor_recommendation=None,
        last_checked_at=None,
    )
    assert response.current_version == "1.0.0"


def test_lifecycle_schemas() -> None:
    action = LifecycleActionRequest(target_state=LifecycleState.RETIRED, reason="EOL")
    assert action.target_state == LifecycleState.RETIRED

    history = AssetChangeHistoryResponse(
        id=uuid.uuid4(),
        managed_asset_id=uuid.uuid4(),
        actor_id=None,
        event_type="retired",
        detail={},
        created_at=datetime.now(UTC),
    )
    assert history.event_type == "retired"

    retirement = AssetRetirementResponse(
        id=uuid.uuid4(),
        managed_asset_id=uuid.uuid4(),
        retired_at=datetime.now(UTC),
        retired_by=None,
        reason="EOL",
        disposed_at=None,
        disposal_method=None,
        residual_value_realized=None,
    )
    assert retirement.reason == "EOL"


def test_procurement_and_depreciation_responses() -> None:
    procurement = AssetProcurementResponse(
        id=uuid.uuid4(),
        managed_asset_id=uuid.uuid4(),
        vendor_id=None,
        purchase_order_number="PO-1",
        invoice_number=None,
        cost_center=None,
        acquisition_cost=1000.0,
        purchase_date=None,
        expected_lifetime_months=36,
        financial_metadata={},
    )
    assert procurement.purchase_order_number == "PO-1"

    depreciation = AssetDepreciationResponse(
        id=uuid.uuid4(),
        managed_asset_id=uuid.uuid4(),
        method=DepreciationMethod.STRAIGHT_LINE,
        acquisition_cost=1000.0,
        residual_value=100.0,
        useful_life_months=36,
        book_value=700.0,
        last_computed_at=None,
    )
    assert depreciation.book_value == 700.0


def test_software_and_patch_history_responses() -> None:
    software = AssetSoftwareResponse(
        id=uuid.uuid4(),
        managed_asset_id=uuid.uuid4(),
        name="nginx",
        software_version="1.25.0",
        license_key=None,
        end_of_life_status=SoftwareEndOfLifeStatus.SUPPORTED,
        installed_at=None,
    )
    assert software.name == "nginx"

    patch = AssetPatchHistoryResponse(
        id=uuid.uuid4(),
        managed_asset_id=uuid.uuid4(),
        software_id=software.id,
        patch_name="CVE fix",
        applied_at=datetime.now(UTC),
        outcome=AuditOutcome.SUCCESS,
        notes=None,
    )
    assert patch.outcome == AuditOutcome.SUCCESS
