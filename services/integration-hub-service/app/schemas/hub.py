"""Request and response schemas for the integration hub's own management surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from shared_core.connectors.credentials import CredentialType
from shared_core.enums.health_status import HealthStatus

from app.models.enums import (
    AuditAction,
    ConflictResolution,
    ConnectionStatus,
    ConnectorAuthMethod,
    ConnectorCategory,
    ConnectorLifecycleStatus,
    CredentialStatus,
    DataFormat,
    EventRoutingStatus,
    EventSource,
    FlowRunStatus,
    FlowStatus,
    FlowTrigger,
    MarketplaceStatus,
    ReportFormat,
    ReportKind,
    ReportStatus,
    SyncMode,
    SyncStatus,
    SyncTrigger,
    TransformationKind,
)

# ---- connectors ------------------------------------------------------------------


class ConnectorCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    category: ConnectorCategory
    connector_type: str = Field(min_length=1, max_length=64)
    auth_method: ConnectorAuthMethod = ConnectorAuthMethod.API_KEY
    marketplace_entry_id: UUID | None = None
    description: str | None = None
    owner_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class ConnectorConfigureRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class ConnectorInstallRequest(BaseModel):
    version_number: str = Field(default="1.0.0", min_length=1, max_length=32)


class ConnectorUpgradeRequest(BaseModel):
    version_number: str = Field(min_length=1, max_length=32)


class ConnectorResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    category: ConnectorCategory
    connector_type: str
    marketplace_entry_id: UUID | None
    current_version_number: str | None
    status: ConnectorLifecycleStatus
    auth_method: ConnectorAuthMethod
    config: dict[str, Any]
    owner_id: str | None
    enabled: bool
    consecutive_failures: int
    last_validated_at: datetime | None
    last_health_check_at: datetime | None
    last_sync_at: datetime | None
    tags: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ConnectorCategoryResponse(BaseModel):
    id: UUID
    name: ConnectorCategory
    description: str | None
    built_in: bool

    model_config = {"from_attributes": True}


class ConnectorVersionResponse(BaseModel):
    id: UUID
    connector_id: UUID
    version_number: str
    changelog: str | None
    installed_at: datetime
    installed_by: str | None
    is_current: bool

    model_config = {"from_attributes": True}


# ---- credentials and connections --------------------------------------------------


class CredentialAssignRequest(BaseModel):
    connector_id: UUID
    credential_type: CredentialType
    secret_ref: str | None = None
    raw_value: str | None = None
    refresh_value: str | None = None
    expires_at: datetime | None = None


class CredentialRotateRequest(BaseModel):
    raw_value: str = Field(min_length=1)
    refresh_value: str | None = None
    expires_at: datetime | None = None


class CredentialResponse(BaseModel):
    id: UUID
    connector_id: UUID
    credential_type: CredentialType
    status: CredentialStatus
    secret_ref: str | None
    expires_at: datetime | None
    last_validated_at: datetime | None
    last_rotated_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConnectionTestResponse(BaseModel):
    id: UUID
    connector_id: UUID
    credential_id: UUID | None
    status: ConnectionStatus
    tested_at: datetime
    latency_ms: float | None
    error: str | None
    attempt_number: int

    model_config = {"from_attributes": True}


# ---- synchronization ----------------------------------------------------------------


class SyncTriggerRequest(BaseModel):
    mode: SyncMode = SyncMode.ONE_WAY
    trigger: SyncTrigger = SyncTrigger.MANUAL
    conflict_resolution: ConflictResolution = ConflictResolution.SOURCE_WINS
    records: list[dict[str, Any]] = Field(default_factory=list)
    """The batch this run processes -- see ``SyncService``'s own
    docstring for why this service accepts records from its caller
    rather than reading them from a live third-party system."""


class SyncJobResponse(BaseModel):
    id: UUID
    organization_id: UUID
    connector_id: UUID
    mode: SyncMode
    trigger: SyncTrigger
    status: SyncStatus
    conflict_resolution: ConflictResolution
    started_at: datetime | None
    completed_at: datetime | None
    records_processed: int
    records_succeeded: int
    records_failed: int
    checkpoint: dict[str, Any]
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- transformations --------------------------------------------------------------


class TransformationCreateRequest(BaseModel):
    connector_id: UUID
    name: str = Field(min_length=1, max_length=128)
    kind: TransformationKind
    source_format: DataFormat = DataFormat.JSON
    target_format: DataFormat = DataFormat.JSON
    config: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=0, le=100_000)


class TransformationResponse(BaseModel):
    id: UUID
    connector_id: UUID
    name: str
    kind: TransformationKind
    source_format: DataFormat
    target_format: DataFormat
    config: dict[str, Any]
    priority: int
    enabled: bool

    model_config = {"from_attributes": True}


class TransformationApplyRequest(BaseModel):
    data: Any


# ---- flows --------------------------------------------------------------------------


class FlowCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    definition: dict[str, Any]
    connector_id: UUID | None = None
    description: str | None = None
    trigger: FlowTrigger = FlowTrigger.MANUAL
    schedule_interval_seconds: int | None = Field(default=None, ge=1)


class FlowRunRequest(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)


class FlowResponse(BaseModel):
    id: UUID
    organization_id: UUID
    connector_id: UUID | None
    name: str
    description: str | None
    definition: dict[str, Any]
    status: FlowStatus
    trigger: FlowTrigger
    schedule_interval_seconds: int | None
    enabled: bool
    last_run_status: FlowRunStatus
    last_run_at: datetime | None
    run_count: int
    last_error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FlowRunResultResponse(BaseModel):
    status: str
    context: dict[str, Any]
    steps_executed: list[str]
    error: str | None
    awaiting_step: str | None


# ---- events ---------------------------------------------------------------------


class ConnectorEventIngestRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=128)
    source: EventSource = EventSource.INTERNAL
    connector_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class ConnectorEventResponse(BaseModel):
    id: UUID
    organization_id: UUID
    connector_id: UUID | None
    source: EventSource
    event_type: str
    payload: dict[str, Any]
    routing_status: EventRoutingStatus
    routed_to: list[str]
    correlation_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- health -----------------------------------------------------------------------


class ConnectorHealthResponse(BaseModel):
    id: UUID
    connector_id: UUID
    status: HealthStatus
    latency_ms: float | None
    checked_at: datetime
    error: str | None
    consecutive_failures: int
    recovery_attempted: bool

    model_config = {"from_attributes": True}


# ---- marketplace --------------------------------------------------------------------


class MarketplacePublishRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    category: ConnectorCategory
    description: str | None = None
    publisher: str = "AI-IOS"
    version_number: str = Field(default="1.0.0", min_length=1, max_length=32)
    supported_auth_methods: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class MarketplaceRateRequest(BaseModel):
    rating: float = Field(ge=1.0, le=5.0)


class MarketplaceEntryResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    category: ConnectorCategory
    description: str | None
    publisher: str
    built_in: bool
    status: MarketplaceStatus
    latest_version_number: str
    supported_auth_methods: list[str]
    dependencies: list[str]
    icon_url: str | None
    homepage_url: str | None
    install_count: int
    rating_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- statistics, reports, audit --------------------------------------------------


class StatisticResponse(BaseModel):
    id: UUID
    window_start: datetime
    window_end: datetime
    syncs_attempted: int
    syncs_succeeded: int
    syncs_failed: int
    records_processed: int
    average_latency_ms: float | None
    success_rate: float
    by_connector: dict[str, int]

    model_config = {"from_attributes": True}


class ReportGenerateRequest(BaseModel):
    kind: ReportKind
    report_format: ReportFormat = ReportFormat.JSON
    title: str | None = None


class ReportResponse(BaseModel):
    id: UUID
    kind: ReportKind
    report_format: ReportFormat
    title: str
    status: ReportStatus
    content: dict[str, Any]
    row_count: int | None
    generated_by: str | None
    generated_at: datetime | None
    duration_ms: float | None
    error: str | None

    model_config = {"from_attributes": True}


class AuditEntryResponse(BaseModel):
    id: UUID
    action: AuditAction
    entity_type: str
    entity_id: UUID | None
    entity_reference: str | None
    actor_id: str | None
    actor_type: str
    occurred_at: datetime
    summary: str
    succeeded: bool
    changes: dict[str, Any]
    context: dict[str, Any]

    model_config = {"from_attributes": True}


__all__ = [
    "AuditEntryResponse",
    "ConnectionTestResponse",
    "ConnectorCategoryResponse",
    "ConnectorConfigureRequest",
    "ConnectorCreateRequest",
    "ConnectorEventIngestRequest",
    "ConnectorEventResponse",
    "ConnectorHealthResponse",
    "ConnectorInstallRequest",
    "ConnectorResponse",
    "ConnectorUpgradeRequest",
    "ConnectorVersionResponse",
    "CredentialAssignRequest",
    "CredentialResponse",
    "CredentialRotateRequest",
    "FlowCreateRequest",
    "FlowResponse",
    "FlowRunRequest",
    "FlowRunResultResponse",
    "MarketplaceEntryResponse",
    "MarketplacePublishRequest",
    "MarketplaceRateRequest",
    "ReportGenerateRequest",
    "ReportResponse",
    "StatisticResponse",
    "SyncJobResponse",
    "SyncTriggerRequest",
    "TransformationApplyRequest",
    "TransformationCreateRequest",
    "TransformationResponse",
]
