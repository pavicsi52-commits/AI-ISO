"""Plugin registration, lifecycle, and marketplace surface
(docs/059 "PLUGIN LIFECYCLE", "REST APIs" -- the 15 literal endpoints
docs/059 names, plus the manifest-submission and dependency-declaration
extensions those endpoints require in order to actually work end to end).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.context import get_log_context

from app.api.deps import (
    AuditSvc,
    CurrentUserId,
    DependencySvc,
    InstallationSvc,
    MarketplaceSvc,
    PluginSvc,
    ReportSvc,
    ReviewSvc,
    StatisticsSvc,
)
from app.models.enums import AuditAction, PluginCategory, PluginLifecycleStatus, ReportKind
from app.models.installation import PluginInstallation
from app.schemas.marketplace import (
    PluginDependencyDeclareRequest,
    PluginDependencyResponse,
    PluginInstallationResponse,
    PluginInstallRequest,
    PluginManifestResponse,
    PluginManifestSubmitRequest,
    PluginMarketplaceResponse,
    PluginPublishRequest,
    PluginRegisterRequest,
    PluginResponse,
    PluginReviewResponse,
    PluginReviewSubmitRequest,
    PluginRollbackInstallationRequest,
    PluginUpdateRequest,
    PluginUpgradeInstallationRequest,
    PluginVersionResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/plugins", tags=["Plugins"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


async def _installation_for_plugin(
    installations: InstallationSvc, organization_id: UUID, plugin_id: UUID
) -> PluginInstallation:
    entries = await installations.list_for_org(organization_id, limit=1_000)
    for entry in entries:
        if entry.plugin_id == plugin_id:
            return entry
    raise ValidationError(f"Plugin {plugin_id} is not installed in this organization.")


@router.get("", response_model=SuccessResponse[list[PluginResponse]], summary="List plugins")
async def list_plugins(
    organization_id: UUID,
    plugins: PluginSvc,
    category: Annotated[PluginCategory | None, Query()] = None,
    status_filter: Annotated[PluginLifecycleStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[PluginResponse]]:
    """Plugins registered in this organization, newest first."""
    rows = await plugins.list_for_org(
        organization_id, category=category, status=status_filter, limit=limit, offset=offset
    )
    return SuccessResponse(
        message="Plugins listed.",
        data=[PluginResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.get(
    "/marketplace",
    response_model=SuccessResponse[list[PluginMarketplaceResponse]],
    summary="Search the marketplace",
)
async def search_marketplace(
    marketplace: MarketplaceSvc,
    query: Annotated[str | None, Query()] = None,
    featured_only: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[PluginMarketplaceResponse]]:
    """Search published marketplace listings."""
    rows = await marketplace.search(
        query=query, featured_only=featured_only, limit=limit, offset=offset
    )
    return SuccessResponse(
        message="Marketplace listings found.",
        data=[PluginMarketplaceResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.get(
    "/reviews",
    response_model=SuccessResponse[list[PluginReviewResponse]],
    summary="List reviews for a plugin",
)
async def list_reviews(
    plugin_id: UUID,
    reviews: ReviewSvc,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[PluginReviewResponse]]:
    """A plugin's own published reviews, newest first."""
    rows = await reviews.list_published(plugin_id, limit=limit, offset=offset)
    return SuccessResponse(
        message="Reviews listed.",
        data=[PluginReviewResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.post(
    "/reviews",
    response_model=SuccessResponse[PluginReviewResponse],
    status_code=201,
    summary="Submit a review",
)
async def submit_review(
    organization_id: UUID, plugin_id: UUID, body: PluginReviewSubmitRequest, reviews: ReviewSvc
) -> SuccessResponse[PluginReviewResponse]:
    """Submit (or update) a review for a plugin."""
    review = await reviews.submit(
        organization_id,
        plugin_id,
        reviewer_id=body.reviewer_id,
        rating=body.rating,
        title=body.title,
        body=body.body,
        installed_version_number=body.installed_version_number,
        verified_install=body.verified_install,
    )
    return SuccessResponse(
        message="Review submitted.", data=PluginReviewResponse.model_validate(review), meta=_meta()
    )


@router.get("/statistics", summary="Marketplace activity dashboard")
async def get_statistics(
    organization_id: UUID, statistics: StatisticsSvc
) -> SuccessResponse[dict[str, Any]]:
    """The live statistics snapshot a dashboard reads on load."""
    data = await statistics.dashboard(organization_id)
    return SuccessResponse(message="Statistics computed.", data=data, meta=_meta())


@router.get("/reports", summary="List generated reports")
async def list_reports(
    organization_id: UUID,
    reports: ReportSvc,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[dict[str, Any]]]:
    """Reports generated in this organization, newest first."""
    rows = await reports.list_for_org(organization_id, limit=limit, offset=offset)
    data = [
        {"id": str(r.id), "kind": str(r.kind), "status": str(r.status), "title": r.title}
        for r in rows
    ]
    return SuccessResponse(message="Reports listed.", data=data, meta=_meta())


@router.post("/reports", summary="Generate a report", status_code=201)
async def generate_report(
    organization_id: UUID, kind: ReportKind, reports: ReportSvc, caller: CurrentUserId
) -> SuccessResponse[dict[str, Any]]:
    """Build and store a new report of the given kind."""
    report = await reports.generate(organization_id, kind=kind, generated_by=str(caller))
    data = {
        "id": str(report.id),
        "kind": str(report.kind),
        "status": str(report.status),
        "row_count": report.row_count,
    }
    return SuccessResponse(message="Report generated.", data=data, meta=_meta())


@router.post(
    "/publish", response_model=SuccessResponse[PluginResponse], summary="Publish a plugin version"
)
async def publish_plugin(
    organization_id: UUID,
    plugin_id: UUID,
    body: PluginPublishRequest,
    plugins: PluginSvc,
    audit: AuditSvc,
) -> SuccessResponse[PluginResponse]:
    """Publish a validated version, making it the plugin's own current version."""
    published = await plugins.publish(
        organization_id, plugin_id, version_number=body.version_number
    )
    await audit.record(
        organization_id,
        action=AuditAction.PLUGIN_PUBLISHED,
        entity_type="plugin",
        entity_id=plugin_id,
        summary=f"Published {published.slug!r} at {body.version_number}.",
    )
    return SuccessResponse(
        message="Plugin published.", data=PluginResponse.model_validate(published), meta=_meta()
    )


@router.get("/{plugin_id}", response_model=SuccessResponse[PluginResponse], summary="Get a plugin")
async def get_plugin(
    organization_id: UUID, plugin_id: UUID, plugins: PluginSvc
) -> SuccessResponse[PluginResponse]:
    """One plugin."""
    found = await plugins.get(organization_id, plugin_id)
    return SuccessResponse(
        message="Plugin found.", data=PluginResponse.model_validate(found), meta=_meta()
    )


@router.post(
    "", response_model=SuccessResponse[PluginResponse], status_code=201, summary="Register a plugin"
)
async def register_plugin(
    organization_id: UUID,
    body: PluginRegisterRequest,
    plugins: PluginSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[PluginResponse]:
    """Register a new plugin definition."""
    created = await plugins.register(
        organization_id,
        slug=body.slug,
        name=body.name,
        category=body.category,
        plugin_type=body.plugin_type,
        publisher_id=body.publisher_id,
        description=body.description,
        homepage_url=body.homepage_url,
        license_name=body.license_name,
        tags=body.tags,
        owner_id=body.owner_id,
    )
    await audit.record(
        organization_id,
        action=AuditAction.PLUGIN_REGISTERED,
        entity_type="plugin",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Registered plugin {created.slug!r}.",
    )
    return SuccessResponse(
        message="Plugin registered.", data=PluginResponse.model_validate(created), meta=_meta()
    )


@router.put(
    "/{plugin_id}", response_model=SuccessResponse[PluginResponse], summary="Update a plugin"
)
async def update_plugin(
    organization_id: UUID, plugin_id: UUID, body: PluginUpdateRequest, plugins: PluginSvc
) -> SuccessResponse[PluginResponse]:
    """Update a plugin's own descriptive metadata."""
    updated = await plugins.update_metadata(
        organization_id,
        plugin_id,
        description=body.description,
        homepage_url=body.homepage_url,
        tags=body.tags,
    )
    return SuccessResponse(
        message="Plugin updated.", data=PluginResponse.model_validate(updated), meta=_meta()
    )


@router.delete(
    "/{plugin_id}", response_model=SuccessResponse[PluginResponse], summary="Archive a plugin"
)
async def archive_plugin(
    organization_id: UUID,
    plugin_id: UUID,
    plugins: PluginSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[PluginResponse]:
    """Archive a plugin -- the lifecycle's own terminal stage."""
    archived = await plugins.archive(organization_id, plugin_id)
    await audit.record(
        organization_id,
        action=AuditAction.PLUGIN_REMOVED,
        entity_type="plugin",
        entity_id=plugin_id,
        actor_id=str(caller),
        summary=f"Archived plugin {archived.slug!r}.",
    )
    return SuccessResponse(
        message="Plugin archived.", data=PluginResponse.model_validate(archived), meta=_meta()
    )


@router.post(
    "/{plugin_id}/manifest",
    response_model=SuccessResponse[PluginManifestResponse],
    status_code=201,
    summary="Submit a version manifest",
)
async def submit_manifest(
    organization_id: UUID, plugin_id: UUID, body: PluginManifestSubmitRequest, plugins: PluginSvc
) -> SuccessResponse[PluginManifestResponse]:
    """Submit a new version with its own manifest for validation."""
    _version, manifest_entry = await plugins.submit_manifest(
        organization_id,
        plugin_id,
        version_number=body.version_number,
        manifest=body.manifest,
        changelog=body.changelog,
    )
    return SuccessResponse(
        message="Manifest submitted.",
        data=PluginManifestResponse.model_validate(manifest_entry),
        meta=_meta(),
    )


@router.get(
    "/{plugin_id}/versions",
    response_model=SuccessResponse[list[PluginVersionResponse]],
    summary="List a plugin's own version history",
)
async def list_versions(
    organization_id: UUID, plugin_id: UUID, plugins: PluginSvc
) -> SuccessResponse[list[PluginVersionResponse]]:
    """A plugin's own version history, newest first."""
    rows = await plugins.list_versions(organization_id, plugin_id)
    return SuccessResponse(
        message="Versions listed.",
        data=[PluginVersionResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.get(
    "/{plugin_id}/dependencies",
    response_model=SuccessResponse[list[PluginDependencyResponse]],
    summary="List a plugin's own dependencies",
)
async def list_dependencies(
    plugin_id: UUID, dependencies: DependencySvc
) -> SuccessResponse[list[PluginDependencyResponse]]:
    """Every dependency declared by a plugin."""
    rows = await dependencies.list_for_plugin(plugin_id)
    return SuccessResponse(
        message="Dependencies listed.",
        data=[PluginDependencyResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.post(
    "/{plugin_id}/dependencies",
    response_model=SuccessResponse[PluginDependencyResponse],
    status_code=201,
    summary="Declare a dependency",
)
async def declare_dependency(
    organization_id: UUID,
    plugin_id: UUID,
    body: PluginDependencyDeclareRequest,
    dependencies: DependencySvc,
) -> SuccessResponse[PluginDependencyResponse]:
    """Declare a new dependency edge.

    Raises:
        ConflictError: If this edge would create a circular dependency chain.
    """
    created = await dependencies.declare(
        organization_id,
        plugin_id,
        depends_on_plugin_id=body.depends_on_plugin_id,
        version_constraint=body.version_constraint,
        optional=body.optional,
    )
    return SuccessResponse(
        message="Dependency declared.",
        data=PluginDependencyResponse.model_validate(created),
        meta=_meta(),
    )


@router.post(
    "/{plugin_id}/install",
    response_model=SuccessResponse[PluginInstallationResponse],
    status_code=201,
    summary="Install a plugin",
)
async def install_plugin(
    organization_id: UUID,
    plugin_id: UUID,
    body: PluginInstallRequest,
    installations: InstallationSvc,
    audit: AuditSvc,
) -> SuccessResponse[PluginInstallationResponse]:
    """Install a published plugin into this organization."""
    installed = await installations.install(
        organization_id, plugin_id, trigger=body.trigger, installed_by=body.installed_by
    )
    await audit.record(
        organization_id,
        action=AuditAction.PLUGIN_INSTALLED,
        entity_type="plugin",
        entity_id=plugin_id,
        summary=f"Installed plugin {plugin_id} at {installed.installed_version_number}.",
    )
    return SuccessResponse(
        message="Plugin installed.",
        data=PluginInstallationResponse.model_validate(installed),
        meta=_meta(),
    )


@router.post(
    "/{plugin_id}/activate",
    response_model=SuccessResponse[PluginInstallationResponse],
    summary="Activate an installed plugin",
)
async def activate_plugin(
    organization_id: UUID, plugin_id: UUID, installations: InstallationSvc, audit: AuditSvc
) -> SuccessResponse[PluginInstallationResponse]:
    """Activate this organization's own installation of a plugin."""
    installation = await _installation_for_plugin(installations, organization_id, plugin_id)
    activated = await installations.activate(organization_id, installation.id)
    await audit.record(
        organization_id,
        action=AuditAction.PLUGIN_ACTIVATED,
        entity_type="plugin",
        entity_id=plugin_id,
        summary=f"Activated plugin {plugin_id}.",
    )
    return SuccessResponse(
        message="Plugin activated.",
        data=PluginInstallationResponse.model_validate(activated),
        meta=_meta(),
    )


@router.post(
    "/{plugin_id}/disable",
    response_model=SuccessResponse[PluginInstallationResponse],
    summary="Disable an installed plugin",
)
async def disable_plugin(
    organization_id: UUID, plugin_id: UUID, installations: InstallationSvc, audit: AuditSvc
) -> SuccessResponse[PluginInstallationResponse]:
    """Disable this organization's own installation of a plugin."""
    installation = await _installation_for_plugin(installations, organization_id, plugin_id)
    disabled = await installations.disable(organization_id, installation.id)
    await audit.record(
        organization_id,
        action=AuditAction.PLUGIN_DISABLED,
        entity_type="plugin",
        entity_id=plugin_id,
        summary=f"Disabled plugin {plugin_id}.",
    )
    return SuccessResponse(
        message="Plugin disabled.",
        data=PluginInstallationResponse.model_validate(disabled),
        meta=_meta(),
    )


@router.post(
    "/{plugin_id}/upgrade",
    response_model=SuccessResponse[PluginInstallationResponse],
    summary="Upgrade an installed plugin",
)
async def upgrade_plugin(
    organization_id: UUID,
    plugin_id: UUID,
    body: PluginUpgradeInstallationRequest,
    installations: InstallationSvc,
    audit: AuditSvc,
) -> SuccessResponse[PluginInstallationResponse]:
    """Upgrade this organization's own installation to a newer version."""
    installation = await _installation_for_plugin(installations, organization_id, plugin_id)
    upgraded = await installations.upgrade(
        organization_id,
        installation.id,
        to_version_number=body.to_version_number,
        strategy=body.strategy,
        initiated_by=body.initiated_by,
    )
    await audit.record(
        organization_id,
        action=AuditAction.PLUGIN_UPGRADED,
        entity_type="plugin",
        entity_id=plugin_id,
        summary=f"Upgraded plugin {plugin_id} to {body.to_version_number}.",
    )
    return SuccessResponse(
        message="Plugin upgraded.",
        data=PluginInstallationResponse.model_validate(upgraded),
        meta=_meta(),
    )


@router.post(
    "/{plugin_id}/rollback",
    response_model=SuccessResponse[PluginInstallationResponse],
    summary="Roll back an installed plugin",
)
async def rollback_plugin(
    organization_id: UUID,
    plugin_id: UUID,
    body: PluginRollbackInstallationRequest,
    installations: InstallationSvc,
    audit: AuditSvc,
) -> SuccessResponse[PluginInstallationResponse]:
    """Roll this organization's own installation back to an older version."""
    installation = await _installation_for_plugin(installations, organization_id, plugin_id)
    rolled_back = await installations.rollback(
        organization_id,
        installation.id,
        to_version_number=body.to_version_number,
        reason=body.reason,
        initiated_by=body.initiated_by,
    )
    await audit.record(
        organization_id,
        action=AuditAction.PLUGIN_ROLLED_BACK,
        entity_type="plugin",
        entity_id=plugin_id,
        summary=f"Rolled back plugin {plugin_id} to {body.to_version_number}.",
    )
    return SuccessResponse(
        message="Plugin rolled back.",
        data=PluginInstallationResponse.model_validate(rolled_back),
        meta=_meta(),
    )


__all__ = ["router"]
