"""``POST /discovery/scan``, ``/network-scan``, ``/cloud-scan``,
``/kubernetes-scan``, ``/industrial-scan``. Per docs/037 REST list,
"NETWORK DISCOVERY", "CLOUD DISCOVERY", "KUBERNETES DISCOVERY",
"INDUSTRIAL DISCOVERY".

**Ad-hoc profile auto-creation**: ``app/models/discovery_target.py``'s
own ``profile_id`` is a real foreign key, and
``app/services/discovery_execution.py::run_job`` only ever looks up a
job's targets via ``list_for_profile(job.profile_id)`` -- so a target
with no profile can never be picked up by a job. Since
``app/schemas/scan.py``'s own module docstring promises these are "one
call, no setup" endpoints, a request that omits ``profile_id`` gets a
minimal ad-hoc :class:`~app.models.discovery_profile.DiscoveryProfile`
created transparently (see :func:`_resolve_profile_id`) rather than
requiring the caller to set one up first.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context
from shared_core.queue.producer import Producer
from shared_core.types.queue import QueueMessage

from app.api.deps import (
    CredentialSvc,
    CurrentUserId,
    CurrentUserToken,
    JobSvc,
    ProfileSvc,
    TargetSvc,
    get_queue_producer,
)
from app.api.job import job_to_response
from app.models.discovery_job import DiscoveryJob
from app.models.enums import DiscoveryMode, ProfileType, ProtocolType, TargetType
from app.schemas.job import DiscoveryJobResponse
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.scan import (
    CloudScanRequest,
    IndustrialScanRequest,
    InlineCredentialSpec,
    KubernetesScanRequest,
    NetworkScanRequest,
    ScanRequest,
)
from app.workers.discovery_worker import DISCOVERY_QUEUE_NAME

router = APIRouter(prefix="/discovery", tags=["Scan"])

_KUBERNETES_CLOUD_PROTOCOL = ProtocolType.HTTPS
"""Cloud/Kubernetes enumeration targets skip protocol-scanner dispatch
entirely (``discovery_execution.py`` routes them to an
:class:`~app.scanners.enumeration.EnumerationProvider` by
``target_type`` alone), but ``DiscoveryTarget.protocol`` is a required
column -- every cloud/Kubernetes API this service talks to is reached
over HTTPS, so that's the one real, non-arbitrary value to record.
"""


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


async def _resolve_profile_id(
    profiles: ProfileSvc,
    *,
    organization_id: UUID,
    profile_id: UUID | None,
    profile_type: ProfileType,
    protocols: list[ProtocolType],
) -> UUID:
    """Return *profile_id* if given, else a freshly-created ad-hoc profile's id."""
    if profile_id is not None:
        return profile_id
    profile = await profiles.create(
        organization_id=organization_id,
        name=f"ad-hoc-{profile_type.value}-{uuid4()}",
        description="Auto-created for an ad-hoc scan request with no profile_id.",
        profile_type=profile_type,
        protocols=protocols,
        default_ports={},
        timeout_seconds=30,
        concurrency_limit=10,
    )
    return profile.id


async def _maybe_create_credential(
    credentials: CredentialSvc,
    *,
    organization_id: UUID,
    spec: InlineCredentialSpec | None,
    protocol: ProtocolType,
) -> UUID | None:
    """Create the backing :class:`~app.models.discovery_credential
    .DiscoveryCredential` row *spec* names, or ``None`` if no credential
    was supplied.
    """
    if spec is None:
        return None
    credential = await credentials.create_from_spec(
        spec, organization_id=organization_id, protocol=protocol
    )
    return credential.id


async def _create_and_queue_job(
    jobs: JobSvc,
    producer: Producer,
    *,
    organization_id: UUID,
    profile_id: UUID,
    caller_id: UUID,
    caller_token: str,
    mode: DiscoveryMode,
) -> DiscoveryJob:
    """Queue the job the newly-registered target(s) will be probed by."""
    job = await jobs.create_job(
        organization_id=organization_id,
        profile_id=profile_id,
        mode=mode,
        triggered_by=caller_id,
    )
    message: QueueMessage = {"job_id": str(job.id), "caller_token": caller_token}
    await producer.publish(DISCOVERY_QUEUE_NAME, message)
    return job


@router.post("/scan", response_model=SuccessResponse[DiscoveryJobResponse], status_code=202)
async def scan(
    body: ScanRequest,
    profiles: ProfileSvc,
    targets: TargetSvc,
    credentials: CredentialSvc,
    jobs: JobSvc,
    caller_id: CurrentUserId,
    caller_token: CurrentUserToken,
    producer: Annotated[Producer, Depends(get_queue_producer)],
) -> SuccessResponse[DiscoveryJobResponse]:
    """Queue a single ad-hoc protocol probe."""
    profile_id = await _resolve_profile_id(
        profiles,
        organization_id=body.organization_id,
        profile_id=body.profile_id,
        profile_type=ProfileType.CUSTOM,
        protocols=[body.protocol],
    )
    credential_id = await _maybe_create_credential(
        credentials,
        organization_id=body.organization_id,
        spec=body.credential,
        protocol=body.protocol,
    )
    await targets.create(
        organization_id=body.organization_id,
        profile_id=profile_id,
        target_type=TargetType.HOST,
        address=body.address,
        protocol=body.protocol,
        port=body.port,
        credential_id=credential_id,
    )
    job = await _create_and_queue_job(
        jobs,
        producer,
        organization_id=body.organization_id,
        profile_id=profile_id,
        caller_id=caller_id,
        caller_token=caller_token,
        mode=DiscoveryMode.MANUAL,
    )
    return SuccessResponse(message="Scan queued.", data=job_to_response(job), meta=_meta())


@router.post("/network-scan", response_model=SuccessResponse[DiscoveryJobResponse], status_code=202)
async def network_scan(
    body: NetworkScanRequest,
    profiles: ProfileSvc,
    targets: TargetSvc,
    credentials: CredentialSvc,
    jobs: JobSvc,
    caller_id: CurrentUserId,
    caller_token: CurrentUserToken,
    producer: Annotated[Producer, Depends(get_queue_producer)],
) -> SuccessResponse[DiscoveryJobResponse]:
    """Queue a multi-address, multi-protocol network sweep ("Network Discovery")."""
    profile_id = await _resolve_profile_id(
        profiles,
        organization_id=body.organization_id,
        profile_id=body.profile_id,
        profile_type=ProfileType.NETWORK_SCAN,
        protocols=body.protocols,
    )
    credential_id = await _maybe_create_credential(
        credentials,
        organization_id=body.organization_id,
        spec=body.credential,
        protocol=body.protocols[0],
    )
    for address in body.addresses:
        for protocol in body.protocols:
            await targets.create(
                organization_id=body.organization_id,
                profile_id=profile_id,
                target_type=TargetType.HOST,
                address=address,
                protocol=protocol,
                port=body.ports.get(address),
                credential_id=credential_id,
            )
    job = await _create_and_queue_job(
        jobs,
        producer,
        organization_id=body.organization_id,
        profile_id=profile_id,
        caller_id=caller_id,
        caller_token=caller_token,
        mode=DiscoveryMode.FULL_SCAN,
    )
    return SuccessResponse(message="Network scan queued.", data=job_to_response(job), meta=_meta())


@router.post("/cloud-scan", response_model=SuccessResponse[DiscoveryJobResponse], status_code=202)
async def cloud_scan(
    body: CloudScanRequest,
    profiles: ProfileSvc,
    targets: TargetSvc,
    credentials: CredentialSvc,
    jobs: JobSvc,
    caller_id: CurrentUserId,
    caller_token: CurrentUserToken,
    producer: Annotated[Producer, Depends(get_queue_producer)],
) -> SuccessResponse[DiscoveryJobResponse]:
    """Queue enumeration of one cloud account ("Cloud Discovery")."""
    profile_id = await _resolve_profile_id(
        profiles,
        organization_id=body.organization_id,
        profile_id=body.profile_id,
        profile_type=ProfileType.CLOUD_SCAN,
        protocols=[_KUBERNETES_CLOUD_PROTOCOL],
    )
    credential_id = await _maybe_create_credential(
        credentials,
        organization_id=body.organization_id,
        spec=body.credential,
        protocol=_KUBERNETES_CLOUD_PROTOCOL,
    )
    await targets.create(
        organization_id=body.organization_id,
        profile_id=profile_id,
        target_type=TargetType.CLOUD_ACCOUNT,
        address=body.address,
        protocol=_KUBERNETES_CLOUD_PROTOCOL,
        credential_id=credential_id,
        metadata={"cloud_vendor": body.cloud_vendor},
    )
    job = await _create_and_queue_job(
        jobs,
        producer,
        organization_id=body.organization_id,
        profile_id=profile_id,
        caller_id=caller_id,
        caller_token=caller_token,
        mode=DiscoveryMode.MANUAL,
    )
    return SuccessResponse(message="Cloud scan queued.", data=job_to_response(job), meta=_meta())


@router.post(
    "/kubernetes-scan", response_model=SuccessResponse[DiscoveryJobResponse], status_code=202
)
async def kubernetes_scan(
    body: KubernetesScanRequest,
    profiles: ProfileSvc,
    targets: TargetSvc,
    credentials: CredentialSvc,
    jobs: JobSvc,
    caller_id: CurrentUserId,
    caller_token: CurrentUserToken,
    producer: Annotated[Producer, Depends(get_queue_producer)],
) -> SuccessResponse[DiscoveryJobResponse]:
    """Queue enumeration of one Kubernetes cluster ("Kubernetes Discovery")."""
    profile_id = await _resolve_profile_id(
        profiles,
        organization_id=body.organization_id,
        profile_id=body.profile_id,
        profile_type=ProfileType.KUBERNETES_SCAN,
        protocols=[_KUBERNETES_CLOUD_PROTOCOL],
    )
    credential_id = await _maybe_create_credential(
        credentials,
        organization_id=body.organization_id,
        spec=body.credential,
        protocol=_KUBERNETES_CLOUD_PROTOCOL,
    )
    await targets.create(
        organization_id=body.organization_id,
        profile_id=profile_id,
        target_type=TargetType.KUBERNETES_CLUSTER,
        address=body.address,
        protocol=_KUBERNETES_CLOUD_PROTOCOL,
        credential_id=credential_id,
    )
    job = await _create_and_queue_job(
        jobs,
        producer,
        organization_id=body.organization_id,
        profile_id=profile_id,
        caller_id=caller_id,
        caller_token=caller_token,
        mode=DiscoveryMode.MANUAL,
    )
    return SuccessResponse(
        message="Kubernetes scan queued.", data=job_to_response(job), meta=_meta()
    )


@router.post(
    "/industrial-scan", response_model=SuccessResponse[DiscoveryJobResponse], status_code=202
)
async def industrial_scan(
    body: IndustrialScanRequest,
    profiles: ProfileSvc,
    targets: TargetSvc,
    credentials: CredentialSvc,
    jobs: JobSvc,
    caller_id: CurrentUserId,
    caller_token: CurrentUserToken,
    producer: Annotated[Producer, Depends(get_queue_producer)],
) -> SuccessResponse[DiscoveryJobResponse]:
    """Queue an OT/industrial protocol sweep ("Industrial Discovery")."""
    profile_id = await _resolve_profile_id(
        profiles,
        organization_id=body.organization_id,
        profile_id=body.profile_id,
        profile_type=ProfileType.INDUSTRIAL_SCAN,
        protocols=body.protocols,
    )
    credential_id = await _maybe_create_credential(
        credentials,
        organization_id=body.organization_id,
        spec=body.credential,
        protocol=body.protocols[0],
    )
    for address in body.addresses:
        for protocol in body.protocols:
            await targets.create(
                organization_id=body.organization_id,
                profile_id=profile_id,
                target_type=TargetType.INDUSTRIAL_NETWORK,
                address=address,
                protocol=protocol,
                credential_id=credential_id,
            )
    job = await _create_and_queue_job(
        jobs,
        producer,
        organization_id=body.organization_id,
        profile_id=profile_id,
        caller_id=caller_id,
        caller_token=caller_token,
        mode=DiscoveryMode.MANUAL,
    )
    return SuccessResponse(
        message="Industrial scan queued.", data=job_to_response(job), meta=_meta()
    )


__all__ = ["router"]
