"""Request and response schemas for the plugin marketplace's own management surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    InstallationTrigger,
    ManifestValidationStatus,
    MarketplaceListingStatus,
    PackageFormat,
    PermissionGrantStatus,
    PluginCategory,
    PluginInstallationStatus,
    PluginLifecycleStatus,
    PluginPermissionCategory,
    PluginType,
    PublisherType,
    PublisherVerificationStatus,
    ReviewStatus,
    RollbackStatus,
    UpgradeStatus,
    UpgradeStrategy,
)

# ---- plugins ----------------------------------------------------------------------


class PluginRegisterRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    category: PluginCategory
    plugin_type: PluginType
    publisher_id: UUID | None = None
    description: str | None = None
    homepage_url: str | None = None
    license_name: str | None = Field(default=None, alias="license")
    tags: list[str] = Field(default_factory=list)
    owner_id: str | None = None

    model_config = {"populate_by_name": True}


class PluginManifestSubmitRequest(BaseModel):
    version_number: str = Field(min_length=1, max_length=32)
    manifest: dict[str, Any]
    changelog: str | None = None


class PluginPublishRequest(BaseModel):
    version_number: str = Field(min_length=1, max_length=32)


class PluginUpdateRequest(BaseModel):
    description: str | None = None
    homepage_url: str | None = None
    tags: list[str] | None = None


class PluginResponse(BaseModel):
    id: UUID
    organization_id: UUID
    slug: str
    name: str
    description: str | None
    category: PluginCategory
    plugin_type: PluginType
    publisher_id: UUID | None
    status: PluginLifecycleStatus
    current_version_number: str | None
    homepage_url: str | None
    tags: list[str]
    owner_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PluginVersionResponse(BaseModel):
    id: UUID
    plugin_id: UUID
    version_number: str
    changelog: str | None
    entry_points: list[str]
    is_current: bool
    released_at: datetime

    model_config = {"from_attributes": True}


class PluginManifestResponse(BaseModel):
    id: UUID
    plugin_id: UUID
    plugin_version_id: UUID
    validation_status: ManifestValidationStatus
    validation_errors: list[str]
    checksum: str | None

    model_config = {"from_attributes": True}


# ---- packages -----------------------------------------------------------------------


class PluginPackageBuildRequest(BaseModel):
    files: dict[str, str] = Field(description="archive path -> base64-encoded file content")
    package_format: PackageFormat = PackageFormat.TAR_GZ
    signer_id: str | None = None
    signing_private_key_pem: str | None = None
    signer_key_fingerprint: str | None = None


class PluginPackageVerifyRequest(BaseModel):
    public_key_pem: str


class PluginPackageResponse(BaseModel):
    id: UUID
    plugin_id: UUID
    plugin_version_id: UUID
    package_format: PackageFormat
    storage_key: str
    size_bytes: int
    checksum: str
    signature_verified: bool | None

    model_config = {"from_attributes": True}


# ---- dependencies -------------------------------------------------------------------


class PluginDependencyDeclareRequest(BaseModel):
    depends_on_plugin_id: UUID
    version_constraint: str = "*"
    optional: bool = False


class PluginDependencyResponse(BaseModel):
    id: UUID
    plugin_id: UUID
    depends_on_plugin_id: UUID
    version_constraint: str
    optional: bool

    model_config = {"from_attributes": True}


# ---- permissions ----------------------------------------------------------------------


class PluginPermissionRequestRequest(BaseModel):
    category: PluginPermissionCategory
    scope: str | None = None
    justification: str | None = None


class PluginPermissionDecisionRequest(BaseModel):
    decided_by: str | None = None


class PluginPermissionResponse(BaseModel):
    id: UUID
    plugin_installation_id: UUID
    category: PluginPermissionCategory
    scope: str | None
    status: PermissionGrantStatus
    justification: str | None
    decided_by: str | None
    decided_at: datetime | None

    model_config = {"from_attributes": True}


# ---- installations --------------------------------------------------------------------


class PluginInstallRequest(BaseModel):
    trigger: InstallationTrigger = InstallationTrigger.ONLINE
    installed_by: str | None = None


class PluginConfigureRequest(BaseModel):
    configuration: dict[str, Any] = Field(default_factory=dict)


class PluginUpgradeInstallationRequest(BaseModel):
    to_version_number: str = Field(min_length=1, max_length=32)
    strategy: UpgradeStrategy = UpgradeStrategy.MANUAL
    initiated_by: str | None = None


class PluginRollbackInstallationRequest(BaseModel):
    to_version_number: str = Field(min_length=1, max_length=32)
    reason: str | None = None
    initiated_by: str | None = None


class PluginInstallationResponse(BaseModel):
    id: UUID
    organization_id: UUID
    plugin_id: UUID
    installed_version_number: str
    status: PluginInstallationStatus
    trigger: InstallationTrigger
    configuration: dict[str, Any]
    installed_by: str | None
    installed_at: datetime
    activated_at: datetime | None
    disabled_at: datetime | None
    removed_at: datetime | None
    last_error: str | None

    model_config = {"from_attributes": True}


class PluginUpgradeResponse(BaseModel):
    id: UUID
    plugin_installation_id: UUID
    from_version_number: str
    to_version_number: str
    strategy: UpgradeStrategy
    status: UpgradeStatus
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class PluginRollbackResponse(BaseModel):
    id: UUID
    plugin_installation_id: UUID
    from_version_number: str
    to_version_number: str
    status: RollbackStatus
    reason: str | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# ---- health -----------------------------------------------------------------------------


class PluginHealthResponse(BaseModel):
    id: UUID
    plugin_installation_id: UUID
    status: str
    latency_ms: float | None
    checked_at: datetime
    error: str | None
    consecutive_failures: int

    model_config = {"from_attributes": True}


# ---- reviews & ratings --------------------------------------------------------------------


class PluginReviewSubmitRequest(BaseModel):
    reviewer_id: str = Field(min_length=1, max_length=128)
    rating: int = Field(ge=1, le=5)
    title: str | None = None
    body: str | None = None
    installed_version_number: str | None = None
    verified_install: bool = False


class PluginReviewFlagRequest(BaseModel):
    reason: str
    moderated_by: str | None = None


class PluginReviewRespondRequest(BaseModel):
    response: str


class PluginReviewResponse(BaseModel):
    id: UUID
    plugin_id: UUID
    reviewer_id: str
    rating: int
    title: str | None
    body: str | None
    verified_install: bool
    status: ReviewStatus
    publisher_response: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PluginRatingResponse(BaseModel):
    plugin_id: UUID
    average_rating: float
    review_count: int
    rating_1_count: int
    rating_2_count: int
    rating_3_count: int
    rating_4_count: int
    rating_5_count: int

    model_config = {"from_attributes": True}


# ---- publishers ---------------------------------------------------------------------------


class PluginPublisherRegisterRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    publisher_type: PublisherType = PublisherType.INDIVIDUAL
    contact_email: str | None = None
    website_url: str | None = None
    bio: str | None = None


class PluginPublisherTrustKeyRequest(BaseModel):
    public_key_pem: str


class PluginPublisherResponse(BaseModel):
    id: UUID
    organization_id: UUID
    slug: str
    display_name: str
    publisher_type: PublisherType
    contact_email: str | None
    website_url: str | None
    verification_status: PublisherVerificationStatus
    trusted_signing_key_fingerprint: str | None
    published_plugin_count: int

    model_config = {"from_attributes": True}


# ---- marketplace listings -----------------------------------------------------------------


class PluginMarketplaceListingRequest(BaseModel):
    search_keywords: list[str] = Field(default_factory=list)
    icon_url: str | None = None
    screenshots: list[str] = Field(default_factory=list)
    pricing_summary: str | None = None


class PluginMarketplaceRejectRequest(BaseModel):
    reason: str


class PluginMarketplaceResponse(BaseModel):
    id: UUID
    plugin_id: UUID
    status: MarketplaceListingStatus
    featured: bool
    search_keywords: list[str]
    install_count: int
    active_install_count: int
    icon_url: str | None
    pricing_summary: str | None

    model_config = {"from_attributes": True}


__all__ = [
    "PluginConfigureRequest",
    "PluginDependencyDeclareRequest",
    "PluginDependencyResponse",
    "PluginHealthResponse",
    "PluginInstallRequest",
    "PluginInstallationResponse",
    "PluginManifestResponse",
    "PluginManifestSubmitRequest",
    "PluginMarketplaceListingRequest",
    "PluginMarketplaceRejectRequest",
    "PluginMarketplaceResponse",
    "PluginPackageBuildRequest",
    "PluginPackageResponse",
    "PluginPackageVerifyRequest",
    "PluginPermissionDecisionRequest",
    "PluginPermissionRequestRequest",
    "PluginPermissionResponse",
    "PluginPublishRequest",
    "PluginPublisherRegisterRequest",
    "PluginPublisherResponse",
    "PluginPublisherTrustKeyRequest",
    "PluginRatingResponse",
    "PluginRegisterRequest",
    "PluginResponse",
    "PluginReviewFlagRequest",
    "PluginReviewRespondRequest",
    "PluginReviewResponse",
    "PluginReviewSubmitRequest",
    "PluginRollbackInstallationRequest",
    "PluginRollbackResponse",
    "PluginUpdateRequest",
    "PluginUpgradeInstallationRequest",
    "PluginUpgradeResponse",
    "PluginVersionResponse",
]
