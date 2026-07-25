"""Request schemas for the five ad-hoc scan-trigger endpoints:
``POST /discovery/scan``, ``/network-scan``, ``/cloud-scan``,
``/kubernetes-scan``, ``/industrial-scan``.

Each creates its own :class:`~app.models.discovery_target
.DiscoveryTarget` row(s) inline and immediately queues a
:class:`~app.models.discovery_job.DiscoveryJob` -- unlike
``POST /discovery/jobs``, which runs against targets registered ahead
of time, these are the "one call, no setup" convenience entry points.

**Credentials are supplied inline, not by id**: docs/037's own literal
REST list never names a ``/discovery/credentials`` endpoint --
:class:`~app.models.discovery_credential.DiscoveryCredential` has no
REST surface of its own, the same "required table, no REST list entry"
shape ``services/inventory-service``'s own category/class/type tables
already established this session. A scan request instead carries
:class:`InlineCredentialSpec` (a reference to a
``services/secrets-management-service`` secret plus the metadata
needed to use it), from which ``app/services/discovery_credential.py``
creates the backing :class:`DiscoveryCredential` row as a side effect
-- the real secret material itself is still never accepted or
persisted here, only its id.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import CredentialType, ProtocolType

_DEFAULT_NETWORK_PROTOCOLS = [ProtocolType.TCP, ProtocolType.ICMP, ProtocolType.DNS]
_DEFAULT_INDUSTRIAL_PROTOCOLS = [ProtocolType.MODBUS, ProtocolType.OPC_UA, ProtocolType.BACNET]


class InlineCredentialSpec(BaseModel):
    """A reference to Secrets Management Service material, supplied
    inline on a scan request rather than by a pre-registered
    :class:`~app.models.discovery_credential.DiscoveryCredential` id.
    """

    secret_id: UUID
    credential_type: CredentialType
    name: str = Field(min_length=1, max_length=255)
    username: str | None = None


class ScanRequest(BaseModel):
    """Body of ``POST /discovery/scan`` -- a single ad-hoc probe."""

    organization_id: UUID
    address: str = Field(min_length=1)
    protocol: ProtocolType
    port: int | None = Field(default=None, ge=1, le=65_535)
    credential: InlineCredentialSpec | None = None
    profile_id: UUID | None = None


class NetworkScanRequest(BaseModel):
    """Body of ``POST /discovery/network-scan`` -- a multi-address,
    multi-protocol network sweep.
    """

    organization_id: UUID
    addresses: list[str] = Field(min_length=1)
    protocols: list[ProtocolType] = Field(default_factory=lambda: list(_DEFAULT_NETWORK_PROTOCOLS))
    ports: dict[str, int] = Field(default_factory=dict)
    credential: InlineCredentialSpec | None = None
    profile_id: UUID | None = None


class CloudScanRequest(BaseModel):
    """Body of ``POST /discovery/cloud-scan`` -- enumerate one cloud account."""

    organization_id: UUID
    cloud_vendor: str = Field(pattern="^(aws|azure|gcp|oracle|ibm)$")
    address: str = Field(
        min_length=1, description="Account/subscription/project/tenancy identifier."
    )
    credential: InlineCredentialSpec
    profile_id: UUID | None = None


class KubernetesScanRequest(BaseModel):
    """Body of ``POST /discovery/kubernetes-scan`` -- enumerate one cluster."""

    organization_id: UUID
    address: str = Field(min_length=1, description="The cluster's API server URL.")
    credential: InlineCredentialSpec | None = None
    profile_id: UUID | None = None


class IndustrialScanRequest(BaseModel):
    """Body of ``POST /discovery/industrial-scan`` -- an OT/industrial
    protocol sweep.
    """

    organization_id: UUID
    addresses: list[str] = Field(min_length=1)
    protocols: list[ProtocolType] = Field(
        default_factory=lambda: list(_DEFAULT_INDUSTRIAL_PROTOCOLS)
    )
    credential: InlineCredentialSpec | None = None
    profile_id: UUID | None = None


__all__ = [
    "CloudScanRequest",
    "IndustrialScanRequest",
    "InlineCredentialSpec",
    "KubernetesScanRequest",
    "NetworkScanRequest",
    "ScanRequest",
]
