"""``/alerts`` -- the full alert lifecycle REST surface.

Every path here is from docs/045's own literal REST list, plus
``GET /alerts/{id}/history``, ``/notifications``, and
``/correlations`` (added directly -- an alert's own recorded lifecycle,
delivery attempts, and correlation edges are all real, persisted state
that would otherwise be unreachable by any caller, the same "required
capability, no REST list entry" precedent every prior AI-IOS service
has established at least once).

``POST /alerts`` runs the **full ingestion pipeline** (deduplicate,
suppress, raise, correlate) rather than blindly inserting a row --
raising an alert through the API and raising one from an internal
event must behave identically, or deduplication silently stops working
for API-raised alerts.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.enums.severity import Severity
from shared_core.logging.context import get_log_context

from app.api.deps import (
    AcknowledgementSvc,
    AlertSvc,
    CorrelationSvc,
    CurrentUserId,
    DispatchSvc,
    EscalationSvc,
    IngestionSvc,
    NotificationSvc,
)
from app.models.alert_instance import AlertInstance
from app.models.enums import AlertStatus
from app.schemas.acknowledgement import AlertAcknowledgementResponse
from app.schemas.alert import (
    AlertAcknowledgeRequest,
    AlertCreateRequest,
    AlertEscalateRequest,
    AlertHistoryResponse,
    AlertResolveRequest,
    AlertResponse,
    AlertUpdateRequest,
)
from app.schemas.correlation import AlertCorrelationResponse
from app.schemas.notification import AlertNotificationResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def alert_to_response(alert: AlertInstance) -> AlertResponse:
    """Map an :class:`AlertInstance` row onto its own response schema."""
    return AlertResponse(
        id=alert.id,
        organization_id=alert.organization_id,
        project_id=alert.project_id,
        rule_id=alert.rule_id,
        source=alert.source,
        severity=alert.severity,
        status=alert.status,
        title=alert.title,
        message=alert.message,
        fingerprint=alert.fingerprint,
        source_reference=alert.source_reference,
        assigned_to=alert.assigned_to,
        triggered_at=alert.triggered_at,
        resolved_at=alert.resolved_at,
        closed_at=alert.closed_at,
    )


@router.get("", response_model=SuccessResponse[list[AlertResponse]])
async def list_alerts(
    organization_id: UUID,
    alerts: AlertSvc,
    _caller: CurrentUserId,
    status: AlertStatus | None = None,
    severity: Severity | None = None,
) -> SuccessResponse[list[AlertResponse]]:
    """List alerts, optionally filtered by status and severity."""
    records = await alerts.list_for_org(organization_id, status=status, severity=severity)
    data = [alert_to_response(record) for record in records]
    return SuccessResponse(message="Alerts retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[AlertResponse], status_code=201)
async def create_alert(
    body: AlertCreateRequest,
    ingestion: IngestionSvc,
    dispatch: DispatchSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[AlertResponse]:
    """Raise an alert through the full ingestion pipeline.

    The response message states which path the event actually took
    (created, deduplicated into an existing alert, or suppressed), so a
    caller is never left guessing why no new alert appeared.
    """
    result = await ingestion.ingest(
        organization_id=body.organization_id,
        project_id=body.project_id,
        rule_id=body.rule_id,
        source=body.source,
        severity=body.severity,
        title=body.title,
        message=body.message,
        source_reference=body.source_reference,
    )
    if result.alert.status not in (AlertStatus.SUPPRESSED,):
        await dispatch.dispatch_alert(result.alert)
    return SuccessResponse(
        message=f"Alert {result.outcome!s}.",
        data=alert_to_response(result.alert),
        meta=_meta(),
    )


@router.get("/{alert_id}", response_model=SuccessResponse[AlertResponse])
async def get_alert(
    alert_id: UUID, alerts: AlertSvc, _caller: CurrentUserId
) -> SuccessResponse[AlertResponse]:
    """Return one alert.

    Raises:
        NotFoundError: If no such alert exists.
    """
    alert = await alerts.get_by_id(alert_id)
    return SuccessResponse(message="Alert retrieved.", data=alert_to_response(alert), meta=_meta())


@router.put("/{alert_id}", response_model=SuccessResponse[AlertResponse])
async def update_alert(
    alert_id: UUID, body: AlertUpdateRequest, alerts: AlertSvc, _caller: CurrentUserId
) -> SuccessResponse[AlertResponse]:
    """Update an alert's own mutable fields.

    Raises:
        NotFoundError: If no such alert exists.
    """
    alert = await alerts.update(
        alert_id,
        severity=body.severity,
        title=body.title,
        message=body.message,
        assigned_to=body.assigned_to,
    )
    return SuccessResponse(message="Alert updated.", data=alert_to_response(alert), meta=_meta())


@router.delete("/{alert_id}", response_model=SuccessResponse[AlertResponse])
async def delete_alert(
    alert_id: UUID, alerts: AlertSvc, caller: CurrentUserId
) -> SuccessResponse[AlertResponse]:
    """Close an alert.

    Deliberately a status transition to ``CLOSED``, not a row deletion:
    an alert is an operational record, and deleting it would destroy
    the history every analytics and post-incident figure depends on.

    Raises:
        NotFoundError: If no such alert exists.
        ConflictError: If the alert cannot be closed from its own current status.
    """
    alert = await alerts.transition(
        alert_id, AlertStatus.CLOSED, changed_by=caller, reason="Closed via API."
    )
    return SuccessResponse(message="Alert closed.", data=alert_to_response(alert), meta=_meta())


@router.post("/{alert_id}/acknowledge", response_model=SuccessResponse[AlertResponse])
async def acknowledge_alert(
    alert_id: UUID,
    body: AlertAcknowledgeRequest,
    alerts: AlertSvc,
    acknowledgements: AcknowledgementSvc,
    caller: CurrentUserId,
) -> SuccessResponse[AlertResponse]:
    """Acknowledge an alert.

    Raises:
        NotFoundError: If no such alert exists.
        ConflictError: If the alert cannot be acknowledged from its own current status.
    """
    alert = await alerts.transition(
        alert_id, AlertStatus.ACKNOWLEDGED, changed_by=caller, reason=body.comment
    )
    await acknowledgements.record(
        organization_id=alert.organization_id,
        project_id=alert.project_id,
        alert_id=alert.id,
        acknowledged_by=caller,
        comment=body.comment,
    )
    return SuccessResponse(
        message="Alert acknowledged.", data=alert_to_response(alert), meta=_meta()
    )


@router.post("/{alert_id}/resolve", response_model=SuccessResponse[AlertResponse])
async def resolve_alert(
    alert_id: UUID,
    body: AlertResolveRequest,
    alerts: AlertSvc,
    acknowledgements: AcknowledgementSvc,
    caller: CurrentUserId,
) -> SuccessResponse[AlertResponse]:
    """Resolve an alert.

    Raises:
        NotFoundError: If no such alert exists.
        ConflictError: If the alert cannot be resolved from its own current status.
    """
    alert = await alerts.transition(
        alert_id, AlertStatus.RESOLVED, changed_by=caller, reason=body.resolution_notes
    )
    if body.resolution_notes is not None:
        await acknowledgements.record(
            organization_id=alert.organization_id,
            project_id=alert.project_id,
            alert_id=alert.id,
            acknowledged_by=caller,
            resolution_notes=body.resolution_notes,
        )
    return SuccessResponse(message="Alert resolved.", data=alert_to_response(alert), meta=_meta())


@router.post("/{alert_id}/escalate", response_model=SuccessResponse[AlertResponse])
async def escalate_alert(
    alert_id: UUID,
    body: AlertEscalateRequest,
    alerts: AlertSvc,
    policies: EscalationSvc,
    caller: CurrentUserId,
) -> SuccessResponse[AlertResponse]:
    """Escalate an alert, optionally naming the policy that justifies it.

    Raises:
        NotFoundError: If no such alert (or policy) exists.
        ConflictError: If the alert cannot be escalated from its own current status.
    """
    reason = body.reason
    if body.policy_id is not None:
        policy = await policies.get_by_id(body.policy_id)
        reason = reason or f"Escalated under policy {policy.name!r}."
    alert = await alerts.transition(
        alert_id, AlertStatus.ESCALATED, changed_by=caller, reason=reason
    )
    return SuccessResponse(message="Alert escalated.", data=alert_to_response(alert), meta=_meta())


@router.get("/{alert_id}/history", response_model=SuccessResponse[list[AlertHistoryResponse]])
async def list_alert_history(
    alert_id: UUID, alerts: AlertSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AlertHistoryResponse]]:
    """Every status transition recorded for an alert ("Audit History")."""
    records = await alerts.list_history(alert_id)
    data = [
        AlertHistoryResponse(
            id=record.id,
            alert_id=record.alert_id,
            from_status=record.from_status,
            to_status=record.to_status,
            changed_by=record.changed_by,
            reason=record.reason,
            changed_at=record.changed_at,
        )
        for record in records
    ]
    return SuccessResponse(message="Alert history retrieved.", data=data, meta=_meta())


@router.get(
    "/{alert_id}/acknowledgements",
    response_model=SuccessResponse[list[AlertAcknowledgementResponse]],
)
async def list_alert_acknowledgements(
    alert_id: UUID, acknowledgements: AcknowledgementSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AlertAcknowledgementResponse]]:
    """Every acknowledgement recorded for an alert."""
    records = await acknowledgements.list_for_alert(alert_id)
    data = [
        AlertAcknowledgementResponse(
            id=record.id,
            alert_id=record.alert_id,
            acknowledgement_type=record.acknowledgement_type,
            acknowledged_by=record.acknowledged_by,
            comment=record.comment,
            resolution_notes=record.resolution_notes,
            acknowledged_at=record.acknowledged_at,
        )
        for record in records
    ]
    return SuccessResponse(message="Alert acknowledgements retrieved.", data=data, meta=_meta())


@router.get(
    "/{alert_id}/notifications",
    response_model=SuccessResponse[list[AlertNotificationResponse]],
)
async def list_alert_notifications(
    alert_id: UUID, notifications: NotificationSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AlertNotificationResponse]]:
    """Every notification delivery attempt for an alert ("Delivery Tracking")."""
    records = await notifications.list_for_alert(alert_id)
    data = [
        AlertNotificationResponse(
            id=record.id,
            alert_id=record.alert_id,
            route_id=record.route_id,
            channel=record.channel,
            status=record.status,
            retry_count=record.retry_count,
            error_message=record.error_message,
            sent_at=record.sent_at,
        )
        for record in records
    ]
    return SuccessResponse(message="Alert notifications retrieved.", data=data, meta=_meta())


@router.post("/notifications/retry", response_model=SuccessResponse[int], status_code=200)
async def retry_failed_notifications(
    organization_id: UUID, notifications: NotificationSvc, _caller: CurrentUserId
) -> SuccessResponse[int]:
    """Re-attempt every failed notification delivery ("NOTIFICATIONS": Retry).

    Added beyond docs/045's own literal REST list: "Retry" is an
    explicit NOTIFICATIONS support line, and without this there is no
    way to trigger one.
    """
    attempted = await notifications.retry_failed(organization_id)
    return SuccessResponse(
        message="Failed notifications re-attempted.", data=attempted, meta=_meta()
    )


@router.get(
    "/{alert_id}/correlations",
    response_model=SuccessResponse[list[AlertCorrelationResponse]],
)
async def list_alert_correlations(
    alert_id: UUID, correlation: CorrelationSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AlertCorrelationResponse]]:
    """Every alert correlated to this one as a downstream symptom."""
    records = await correlation.list_children(alert_id)
    data = [
        AlertCorrelationResponse(
            id=record.id,
            parent_alert_id=record.parent_alert_id,
            child_alert_id=record.child_alert_id,
            correlation_type=record.correlation_type,
            correlated_at=record.correlated_at,
        )
        for record in records
    ]
    return SuccessResponse(message="Alert correlations retrieved.", data=data, meta=_meta())


__all__ = ["alert_to_response", "router"]
