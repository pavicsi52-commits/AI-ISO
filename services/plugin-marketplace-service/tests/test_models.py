"""Tests for the ORM models in ``app.models`` against the real database.

Every test stores a row through the ``db_session`` (SAVEPOINT-isolated,
auto-rolled-back) fixture, forces a real reload via
``db_session.refresh``, and asserts the field values -- including that
enum columns really do come back as plain ``str`` (the "enum-as-str"
convention documented on ``app.models.enums``), not the enum member,
since SQLAlchemy loads a ``String`` column as ``str`` regardless of the
``Mapped[SomeEnum]`` annotation. See
``services/alerting-service/tests/test_enum_persistence.py`` for the
same established precedent this module follows.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditAction,
    HealthStatus,
    InstallationTrigger,
    ManifestValidationStatus,
    MarketplaceListingStatus,
    PackageFormat,
    PermissionGrantStatus,
    Plugin,
    PluginAudit,
    PluginCategory,
    PluginDependency,
    PluginHealth,
    PluginInstallation,
    PluginInstallationStatus,
    PluginManifestEntry,
    PluginMarketplaceEntry,
    PluginPackage,
    PluginPermissionCategory,
    PluginPermissionGrant,
    PluginPublisher,
    PluginRating,
    PluginReport,
    PluginReview,
    PluginRollback,
    PluginStatistic,
    PluginType,
    PluginUpgrade,
    PluginVersion,
    PublisherType,
    PublisherVerificationStatus,
    ReportFormat,
    ReportKind,
    ReportStatus,
    ReviewStatus,
    RollbackStatus,
    SignatureAlgorithm,
    UpgradeStatus,
    UpgradeStrategy,
)
from tests.conftest import ago, utcnow

# ---- row builders -----------------------------------------------------------------
#
# Real FK-constrained parent rows, flushed (never committed -- the
# db_session fixture's own SAVEPOINT rolls everything back), so the
# child rows built on top of them satisfy Postgres's real foreign keys.


async def _make_plugin(
    session: AsyncSession, organization_id: uuid.UUID, **overrides: object
) -> Plugin:
    kwargs: dict[str, object] = {
        "organization_id": organization_id,
        "slug": f"plugin-{uuid.uuid4().hex[:10]}",
        "name": "Inventory Sync",
        "category": PluginCategory.INVENTORY,
        "plugin_type": PluginType.CUSTOM_PLUGIN,
    }
    kwargs.update(overrides)
    plugin = Plugin(**kwargs)
    session.add(plugin)
    await session.flush()
    return plugin


async def _make_version(
    session: AsyncSession, organization_id: uuid.UUID, plugin: Plugin, **overrides: object
) -> PluginVersion:
    kwargs: dict[str, object] = {
        "organization_id": organization_id,
        "plugin_id": plugin.id,
        "version_number": "1.0.0",
        "entry_points": ["main:run"],
        "released_at": utcnow(),
    }
    kwargs.update(overrides)
    version = PluginVersion(**kwargs)
    session.add(version)
    await session.flush()
    return version


async def _make_installation(
    session: AsyncSession, organization_id: uuid.UUID, plugin: Plugin, **overrides: object
) -> PluginInstallation:
    kwargs: dict[str, object] = {
        "organization_id": organization_id,
        "plugin_id": plugin.id,
        "installed_version_number": "1.0.0",
        "installed_at": utcnow(),
    }
    kwargs.update(overrides)
    installation = PluginInstallation(**kwargs)
    session.add(installation)
    await session.flush()
    return installation


# ---- Plugin + base mixin ------------------------------------------------------------


async def test_plugin_round_trips_and_base_mixin_fields_are_auto_populated(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(
        db_session,
        organization_id,
        slug="inventory-sync",
        description="Keeps inventory levels synchronized.",
        tags=["inventory", "sync", "automation"],
        homepage_url="https://example.com/plugins/inventory-sync",
        license="MIT",
        owner_id="team-inventory",
    )

    # Auto-populated by the base mixin, before any DB round trip.
    assert isinstance(plugin.id, uuid.UUID)
    assert plugin.organization_id == organization_id
    assert plugin.created_at is not None
    assert plugin.version == 1
    assert plugin.is_active is True

    await db_session.refresh(plugin)

    # Genuinely reloaded from Postgres: enum columns come back as plain str.
    assert not isinstance(plugin.category, PluginCategory)
    assert not isinstance(plugin.plugin_type, PluginType)
    assert plugin.category == PluginCategory.INVENTORY
    assert plugin.plugin_type == PluginType.CUSTOM_PLUGIN
    assert plugin.slug == "inventory-sync"
    assert plugin.name == "Inventory Sync"
    assert plugin.description == "Keeps inventory levels synchronized."
    assert plugin.tags == ["inventory", "sync", "automation"]
    assert plugin.homepage_url == "https://example.com/plugins/inventory-sync"
    assert plugin.license == "MIT"
    assert plugin.owner_id == "team-inventory"
    assert plugin.publisher_id is None
    assert plugin.current_version_number is None


# ---- PluginVersion -------------------------------------------------------------------


async def test_plugin_version_round_trips_json_columns(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    released_at = utcnow()
    version = await _make_version(
        db_session,
        organization_id,
        plugin,
        version_number="2.1.0",
        changelog="Fixed a bug.",
        compatibility_constraint=">=1.0.0,<3.0.0",
        entry_points=["main:run", "worker:start"],
        configuration_schema={"type": "object", "properties": {"interval": {"type": "integer"}}},
        api_requirements=["inventory.v1", "inventory.v2"],
        health_checks=["/healthz", "/readyz"],
        is_current=False,
        released_by="ci-bot",
    )

    await db_session.refresh(version)

    assert version.plugin_id == plugin.id
    assert version.version_number == "2.1.0"
    assert version.changelog == "Fixed a bug."
    assert version.compatibility_constraint == ">=1.0.0,<3.0.0"
    assert version.entry_points == ["main:run", "worker:start"]
    assert version.configuration_schema == {
        "type": "object",
        "properties": {"interval": {"type": "integer"}},
    }
    assert version.api_requirements == ["inventory.v1", "inventory.v2"]
    assert version.health_checks == ["/healthz", "/readyz"]
    assert version.is_current is False
    assert version.released_by == "ci-bot"
    assert version.released_at.replace(microsecond=0) == released_at.replace(microsecond=0)


async def test_plugin_version_default_compatibility_constraint_is_wildcard(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    version = await _make_version(db_session, organization_id, plugin)
    await db_session.refresh(version)
    assert version.compatibility_constraint == "*"
    assert version.entry_points == ["main:run"]
    assert version.configuration_schema == {}


# ---- PluginManifestEntry --------------------------------------------------------------


async def test_plugin_manifest_entry_round_trips_raw_content_and_enum_status(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    version = await _make_version(db_session, organization_id, plugin)
    raw_content = {
        "name": "Inventory Sync",
        "publisher": "acme-plugins",
        "category": "inventory",
        "type": "custom_plugin",
        "version": "1.0.0",
        "entry_points": ["main:run"],
    }
    manifest = PluginManifestEntry(
        organization_id=organization_id,
        plugin_id=plugin.id,
        plugin_version_id=version.id,
        raw_content=raw_content,
        publisher_name="acme-plugins",
        checksum="a" * 64,
        validation_status=ManifestValidationStatus.VALID,
        validation_errors=[],
        validated_at=utcnow(),
        notes="Looks good.",
    )
    db_session.add(manifest)
    await db_session.flush()
    await db_session.refresh(manifest)

    assert not isinstance(manifest.validation_status, ManifestValidationStatus)
    assert manifest.validation_status == ManifestValidationStatus.VALID
    assert manifest.raw_content == raw_content
    assert manifest.checksum == "a" * 64
    assert manifest.validation_errors == []
    assert manifest.notes == "Looks good."


async def test_plugin_manifest_entry_round_trips_validation_errors_list(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    version = await _make_version(db_session, organization_id, plugin)
    manifest = PluginManifestEntry(
        organization_id=organization_id,
        plugin_id=plugin.id,
        plugin_version_id=version.id,
        raw_content={"name": "X"},
        validation_status=ManifestValidationStatus.INVALID,
        validation_errors=["Missing 'publisher'.", "Unknown category 'bogus'."],
    )
    db_session.add(manifest)
    await db_session.flush()
    await db_session.refresh(manifest)

    assert manifest.validation_status == ManifestValidationStatus.INVALID
    assert manifest.validation_errors == ["Missing 'publisher'.", "Unknown category 'bogus'."]


# ---- PluginPackage -----------------------------------------------------------------------


async def test_plugin_package_round_trips_signing_fields(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    version = await _make_version(db_session, organization_id, plugin)
    package = PluginPackage(
        organization_id=organization_id,
        plugin_id=plugin.id,
        plugin_version_id=version.id,
        package_format=PackageFormat.ZIP,
        storage_key=f"plugin-packages/{plugin.id}/1.0.0.zip",
        size_bytes=123_456,
        checksum="b" * 64,
        signature_algorithm=SignatureAlgorithm.ED25519,
        signature="c" * 88,
        signer_id="publisher-1",
        signer_key_fingerprint="SHA256:abcdef",
        signature_verified=True,
    )
    db_session.add(package)
    await db_session.flush()
    await db_session.refresh(package)

    assert not isinstance(package.package_format, PackageFormat)
    assert package.package_format == PackageFormat.ZIP
    assert not isinstance(package.signature_algorithm, SignatureAlgorithm)
    assert package.signature_algorithm == SignatureAlgorithm.ED25519
    assert package.size_bytes == 123_456
    assert package.checksum == "b" * 64
    assert package.signature_verified is True
    assert package.signer_key_fingerprint == "SHA256:abcdef"


async def test_plugin_package_default_format_is_tar_gz(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    version = await _make_version(db_session, organization_id, plugin)
    package = PluginPackage(
        organization_id=organization_id,
        plugin_id=plugin.id,
        plugin_version_id=version.id,
        storage_key=f"plugin-packages/{plugin.id}/1.0.0.tar.gz",
        size_bytes=42,
        checksum="d" * 64,
    )
    db_session.add(package)
    await db_session.flush()
    await db_session.refresh(package)
    assert package.package_format == PackageFormat.TAR_GZ
    assert package.signature_algorithm is None
    assert package.signature_verified is None


# ---- PluginDependency -----------------------------------------------------------------


async def test_plugin_dependency_round_trips_edge_fields(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id, slug="dependent-plugin")
    depends_on = await _make_plugin(db_session, organization_id, slug="core-utils")
    dependency = PluginDependency(
        organization_id=organization_id,
        plugin_id=plugin.id,
        depends_on_plugin_id=depends_on.id,
        version_constraint=">=2.0.0,<3.0.0",
        optional=True,
    )
    db_session.add(dependency)
    await db_session.flush()
    await db_session.refresh(dependency)

    assert dependency.plugin_id == plugin.id
    assert dependency.depends_on_plugin_id == depends_on.id
    assert dependency.version_constraint == ">=2.0.0,<3.0.0"
    assert dependency.optional is True


async def test_plugin_dependency_defaults(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id, slug="dependent-plugin-2")
    depends_on = await _make_plugin(db_session, organization_id, slug="core-utils-2")
    dependency = PluginDependency(
        organization_id=organization_id,
        plugin_id=plugin.id,
        depends_on_plugin_id=depends_on.id,
    )
    db_session.add(dependency)
    await db_session.flush()
    await db_session.refresh(dependency)
    assert dependency.version_constraint == "*"
    assert dependency.optional is False


# ---- PluginPermissionGrant -----------------------------------------------------------


async def test_plugin_permission_grant_round_trips_enum_category_and_status(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    installation = await _make_installation(db_session, organization_id, plugin)
    grant = PluginPermissionGrant(
        organization_id=organization_id,
        plugin_installation_id=installation.id,
        category=PluginPermissionCategory.FILESYSTEM,
        scope="/data/inventory/*",
        status=PermissionGrantStatus.GRANTED,
        justification="Needs to read inventory CSVs.",
        decided_by="admin-1",
        decided_at=utcnow(),
    )
    db_session.add(grant)
    await db_session.flush()
    await db_session.refresh(grant)

    assert not isinstance(grant.category, PluginPermissionCategory)
    assert grant.category == PluginPermissionCategory.FILESYSTEM
    assert not isinstance(grant.status, PermissionGrantStatus)
    assert grant.status == PermissionGrantStatus.GRANTED
    assert grant.scope == "/data/inventory/*"
    assert grant.justification == "Needs to read inventory CSVs."
    assert grant.decided_by == "admin-1"


async def test_plugin_permission_grant_default_status_is_pending(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    installation = await _make_installation(db_session, organization_id, plugin)
    grant = PluginPermissionGrant(
        organization_id=organization_id,
        plugin_installation_id=installation.id,
        category=PluginPermissionCategory.NETWORK,
    )
    db_session.add(grant)
    await db_session.flush()
    await db_session.refresh(grant)
    assert grant.status == PermissionGrantStatus.PENDING
    assert grant.scope is None
    assert grant.decided_at is None


# ---- PluginInstallation ---------------------------------------------------------------


async def test_plugin_installation_round_trips_configuration_and_enum_fields(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    installation = await _make_installation(
        db_session,
        organization_id,
        plugin,
        status=PluginInstallationStatus.ACTIVE,
        trigger=InstallationTrigger.BULK,
        configuration={"sync_interval_seconds": 300, "enabled_categories": ["inventory"]},
        installed_by="ops-team",
        activated_at=utcnow(),
    )

    await db_session.refresh(installation)

    assert not isinstance(installation.status, PluginInstallationStatus)
    assert installation.status == PluginInstallationStatus.ACTIVE
    assert not isinstance(installation.trigger, InstallationTrigger)
    assert installation.trigger == InstallationTrigger.BULK
    assert installation.configuration == {
        "sync_interval_seconds": 300,
        "enabled_categories": ["inventory"],
    }
    assert installation.installed_by == "ops-team"
    assert installation.activated_at is not None
    assert installation.disabled_at is None
    assert installation.removed_at is None


async def test_plugin_installation_defaults(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    installation = await _make_installation(db_session, organization_id, plugin)
    await db_session.refresh(installation)
    assert installation.status == PluginInstallationStatus.INSTALLING
    assert installation.trigger == InstallationTrigger.ONLINE
    assert installation.configuration == {}


# ---- PluginUpgrade ----------------------------------------------------------------------


async def test_plugin_upgrade_round_trips_strategy_and_status(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    installation = await _make_installation(db_session, organization_id, plugin)
    upgrade = PluginUpgrade(
        organization_id=organization_id,
        plugin_installation_id=installation.id,
        from_version_number="1.0.0",
        to_version_number="1.1.0",
        strategy=UpgradeStrategy.CANARY,
        status=UpgradeStatus.COMPLETED,
        started_at=ago(600),
        completed_at=utcnow(),
        initiated_by="ops-team",
    )
    db_session.add(upgrade)
    await db_session.flush()
    await db_session.refresh(upgrade)

    assert not isinstance(upgrade.strategy, UpgradeStrategy)
    assert upgrade.strategy == UpgradeStrategy.CANARY
    assert not isinstance(upgrade.status, UpgradeStatus)
    assert upgrade.status == UpgradeStatus.COMPLETED
    assert upgrade.from_version_number == "1.0.0"
    assert upgrade.to_version_number == "1.1.0"
    assert upgrade.error is None


async def test_plugin_upgrade_defaults(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    installation = await _make_installation(db_session, organization_id, plugin)
    upgrade = PluginUpgrade(
        organization_id=organization_id,
        plugin_installation_id=installation.id,
        from_version_number="1.0.0",
        to_version_number="1.1.0",
        started_at=utcnow(),
    )
    db_session.add(upgrade)
    await db_session.flush()
    await db_session.refresh(upgrade)
    assert upgrade.strategy == UpgradeStrategy.MANUAL
    assert upgrade.status == UpgradeStatus.PENDING
    assert upgrade.completed_at is None


# ---- PluginRollback ----------------------------------------------------------------------


async def test_plugin_rollback_round_trips_and_references_its_upgrade(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    installation = await _make_installation(db_session, organization_id, plugin)
    upgrade = PluginUpgrade(
        organization_id=organization_id,
        plugin_installation_id=installation.id,
        from_version_number="1.0.0",
        to_version_number="1.1.0",
        started_at=ago(600),
    )
    db_session.add(upgrade)
    await db_session.flush()

    rollback = PluginRollback(
        organization_id=organization_id,
        plugin_installation_id=installation.id,
        plugin_upgrade_id=upgrade.id,
        from_version_number="1.1.0",
        to_version_number="1.0.0",
        status=RollbackStatus.FAILED,
        reason="Upgrade broke health checks.",
        started_at=utcnow(),
        error="Connection refused.",
    )
    db_session.add(rollback)
    await db_session.flush()
    await db_session.refresh(rollback)

    assert rollback.plugin_upgrade_id == upgrade.id
    assert not isinstance(rollback.status, RollbackStatus)
    assert rollback.status == RollbackStatus.FAILED
    assert rollback.reason == "Upgrade broke health checks."
    assert rollback.error == "Connection refused."


async def test_plugin_rollback_plugin_upgrade_id_is_nullable(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    installation = await _make_installation(db_session, organization_id, plugin)
    rollback = PluginRollback(
        organization_id=organization_id,
        plugin_installation_id=installation.id,
        from_version_number="1.1.0",
        to_version_number="1.0.0",
        started_at=utcnow(),
    )
    db_session.add(rollback)
    await db_session.flush()
    await db_session.refresh(rollback)
    assert rollback.plugin_upgrade_id is None
    assert rollback.status == RollbackStatus.PENDING


# ---- PluginReview ----------------------------------------------------------------------


async def test_plugin_review_round_trips_rating_and_status(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    review = PluginReview(
        organization_id=organization_id,
        plugin_id=plugin.id,
        reviewer_id="user-42",
        rating=5,
        title="Excellent",
        body="Works exactly as described.",
        installed_version_number="1.0.0",
        verified_install=True,
        status=ReviewStatus.PUBLISHED,
        publisher_response="Thanks for the kind words!",
        publisher_responded_at=utcnow(),
    )
    db_session.add(review)
    await db_session.flush()
    await db_session.refresh(review)

    assert review.rating == 5
    assert isinstance(review.rating, int)
    assert not isinstance(review.status, ReviewStatus)
    assert review.status == ReviewStatus.PUBLISHED
    assert review.verified_install is True
    assert review.publisher_response == "Thanks for the kind words!"


async def test_plugin_review_flagged_state_round_trips(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    review = PluginReview(
        organization_id=organization_id,
        plugin_id=plugin.id,
        reviewer_id="user-99",
        rating=1,
        status=ReviewStatus.FLAGGED,
        flagged_reason="Spam.",
        moderated_by="moderator-1",
        moderated_at=utcnow(),
    )
    db_session.add(review)
    await db_session.flush()
    await db_session.refresh(review)
    assert review.status == ReviewStatus.FLAGGED
    assert review.flagged_reason == "Spam."
    assert review.moderated_by == "moderator-1"


# ---- PluginRating ------------------------------------------------------------------------


async def test_plugin_rating_round_trips_aggregate_counts(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    rating = PluginRating(
        organization_id=organization_id,
        plugin_id=plugin.id,
        average_rating=4.5,
        review_count=10,
        rating_1_count=0,
        rating_2_count=1,
        rating_3_count=1,
        rating_4_count=2,
        rating_5_count=6,
        recalculated_at=utcnow(),
    )
    db_session.add(rating)
    await db_session.flush()
    await db_session.refresh(rating)

    assert rating.average_rating == 4.5
    assert isinstance(rating.average_rating, float)
    assert rating.review_count == 10
    assert rating.rating_5_count == 6
    assert rating.rating_1_count + rating.rating_2_count + rating.rating_3_count
    assert rating.rating_4_count + rating.rating_5_count == 8


async def test_plugin_rating_defaults(db_session: AsyncSession, organization_id: uuid.UUID) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    rating = PluginRating(organization_id=organization_id, plugin_id=plugin.id)
    db_session.add(rating)
    await db_session.flush()
    await db_session.refresh(rating)
    assert rating.average_rating == 0.0
    assert rating.review_count == 0
    assert rating.recalculated_at is None


# ---- PluginPublisher --------------------------------------------------------------------


async def test_plugin_publisher_round_trips_verification_fields(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    publisher = PluginPublisher(
        organization_id=organization_id,
        slug="acme-plugins",
        display_name="Acme Plugins Co.",
        publisher_type=PublisherType.ORGANIZATION,
        contact_email="publisher@acme.example.com",
        website_url="https://acme.example.com",
        verification_status=PublisherVerificationStatus.VERIFIED,
        verified_at=utcnow(),
        verified_by="admin-1",
        trusted_signing_key_fingerprint="SHA256:deadbeef",
        published_plugin_count=7,
        bio="We build inventory automation plugins.",
    )
    db_session.add(publisher)
    await db_session.flush()
    await db_session.refresh(publisher)

    assert not isinstance(publisher.publisher_type, PublisherType)
    assert publisher.publisher_type == PublisherType.ORGANIZATION
    assert not isinstance(publisher.verification_status, PublisherVerificationStatus)
    assert publisher.verification_status == PublisherVerificationStatus.VERIFIED
    assert publisher.trusted_signing_key_fingerprint == "SHA256:deadbeef"
    assert publisher.published_plugin_count == 7


async def test_plugin_publisher_defaults(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    publisher = PluginPublisher(
        organization_id=organization_id,
        slug="solo-dev",
        display_name="Solo Developer",
    )
    db_session.add(publisher)
    await db_session.flush()
    await db_session.refresh(publisher)
    assert publisher.publisher_type == PublisherType.INDIVIDUAL
    assert publisher.verification_status == PublisherVerificationStatus.UNVERIFIED
    assert publisher.published_plugin_count == 0


# ---- PluginMarketplaceEntry --------------------------------------------------------------


async def test_plugin_marketplace_entry_round_trips_lists_and_enum_status(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    entry = PluginMarketplaceEntry(
        organization_id=organization_id,
        plugin_id=plugin.id,
        status=MarketplaceListingStatus.FEATURED,
        featured=True,
        search_keywords=["inventory", "sync", "automation"],
        install_count=150,
        active_install_count=120,
        icon_url="https://example.com/icon.png",
        screenshots=["https://example.com/s1.png", "https://example.com/s2.png"],
        pricing_summary="Free",
        listed_at=utcnow(),
        approved_by="admin-1",
        approved_at=utcnow(),
    )
    db_session.add(entry)
    await db_session.flush()
    await db_session.refresh(entry)

    assert not isinstance(entry.status, MarketplaceListingStatus)
    assert entry.status == MarketplaceListingStatus.FEATURED
    assert entry.featured is True
    assert entry.search_keywords == ["inventory", "sync", "automation"]
    assert entry.screenshots == ["https://example.com/s1.png", "https://example.com/s2.png"]
    assert entry.install_count == 150
    assert entry.active_install_count == 120


async def test_plugin_marketplace_entry_defaults(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    entry = PluginMarketplaceEntry(organization_id=organization_id, plugin_id=plugin.id)
    db_session.add(entry)
    await db_session.flush()
    await db_session.refresh(entry)
    assert entry.status == MarketplaceListingStatus.DRAFT
    assert entry.featured is False
    assert entry.search_keywords == []
    assert entry.screenshots == []
    assert entry.install_count == 0


# ---- PluginHealth ------------------------------------------------------------------------


async def test_plugin_health_round_trips_shared_core_health_status(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    installation = await _make_installation(db_session, organization_id, plugin)
    health = PluginHealth(
        organization_id=organization_id,
        plugin_installation_id=installation.id,
        status=HealthStatus.DEGRADED,
        latency_ms=87.5,
        checked_at=utcnow(),
        error="Slow response from health endpoint.",
        consecutive_failures=2,
        recovery_attempted=True,
    )
    db_session.add(health)
    await db_session.flush()
    await db_session.refresh(health)

    assert not isinstance(health.status, HealthStatus)
    assert health.status == HealthStatus.DEGRADED
    assert health.latency_ms == 87.5
    assert health.consecutive_failures == 2
    assert health.recovery_attempted is True


async def test_plugin_health_defaults(db_session: AsyncSession, organization_id: uuid.UUID) -> None:
    plugin = await _make_plugin(db_session, organization_id)
    installation = await _make_installation(db_session, organization_id, plugin)
    health = PluginHealth(
        organization_id=organization_id,
        plugin_installation_id=installation.id,
        checked_at=utcnow(),
    )
    db_session.add(health)
    await db_session.flush()
    await db_session.refresh(health)
    assert health.status == HealthStatus.UNKNOWN
    assert health.consecutive_failures == 0
    assert health.recovery_attempted is False


# ---- PluginStatistic ----------------------------------------------------------------------


async def test_plugin_statistic_round_trips_json_by_category(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    statistic = PluginStatistic(
        organization_id=organization_id,
        window_start=ago(3600),
        window_end=utcnow(),
        plugins_published=3,
        installations_attempted=50,
        installations_succeeded=45,
        installations_failed=5,
        upgrades_completed=10,
        rollbacks_completed=1,
        reviews_submitted=8,
        average_rating=4.3,
        by_category={"inventory": 12, "automation": 8, "monitoring": 3},
    )
    db_session.add(statistic)
    await db_session.flush()
    await db_session.refresh(statistic)

    assert statistic.plugins_published == 3
    assert statistic.installations_succeeded == 45
    assert statistic.average_rating == 4.3
    assert statistic.by_category == {"inventory": 12, "automation": 8, "monitoring": 3}


async def test_plugin_statistic_defaults(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    statistic = PluginStatistic(
        organization_id=organization_id, window_start=ago(3600), window_end=utcnow()
    )
    db_session.add(statistic)
    await db_session.flush()
    await db_session.refresh(statistic)
    assert statistic.plugins_published == 0
    assert statistic.average_rating is None
    assert statistic.by_category == {}


# ---- PluginReport --------------------------------------------------------------------------


async def test_plugin_report_round_trips_content_and_enum_kind(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    report = PluginReport(
        organization_id=organization_id,
        kind=ReportKind.MARKETPLACE,
        report_format=ReportFormat.MARKDOWN,
        title="Weekly Marketplace Report",
        status=ReportStatus.COMPLETED,
        content={"total_plugins": 42, "top_category": "inventory"},
        row_count=42,
        generated_by="report-worker",
        generated_at=utcnow(),
        duration_ms=215.75,
    )
    db_session.add(report)
    await db_session.flush()
    await db_session.refresh(report)

    assert not isinstance(report.kind, ReportKind)
    assert report.kind == ReportKind.MARKETPLACE
    assert not isinstance(report.report_format, ReportFormat)
    assert report.report_format == ReportFormat.MARKDOWN
    assert not isinstance(report.status, ReportStatus)
    assert report.status == ReportStatus.COMPLETED
    assert report.content == {"total_plugins": 42, "top_category": "inventory"}
    assert report.row_count == 42
    assert report.duration_ms == 215.75


async def test_plugin_report_defaults(db_session: AsyncSession, organization_id: uuid.UUID) -> None:
    report = PluginReport(
        organization_id=organization_id, kind=ReportKind.AUDIT, title="Audit Report"
    )
    db_session.add(report)
    await db_session.flush()
    await db_session.refresh(report)
    assert report.report_format == ReportFormat.JSON
    assert report.status == ReportStatus.PENDING
    assert report.content == {}
    assert report.error is None


# ---- PluginAudit ---------------------------------------------------------------------------


async def test_plugin_audit_round_trips_changes_and_context_json(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    entity_id = uuid.uuid4()
    audit = PluginAudit(
        organization_id=organization_id,
        action=AuditAction.PLUGIN_INSTALLED,
        entity_type="plugin_installation",
        entity_id=entity_id,
        entity_reference="inventory-sync@1.0.0",
        actor_id="user-42",
        actor_type="user",
        occurred_at=utcnow(),
        summary="Installed inventory-sync 1.0.0.",
        succeeded=True,
        changes={"status": {"from": "installing", "to": "installed"}},
        context={"ip": "127.0.0.1", "user_agent": "pytest"},
        request_id="req-abc-123",
        ip_address="127.0.0.1",
    )
    db_session.add(audit)
    await db_session.flush()
    await db_session.refresh(audit)

    assert not isinstance(audit.action, AuditAction)
    assert audit.action == AuditAction.PLUGIN_INSTALLED
    assert audit.entity_id == entity_id
    assert audit.changes == {"status": {"from": "installing", "to": "installed"}}
    assert audit.context == {"ip": "127.0.0.1", "user_agent": "pytest"}
    assert audit.succeeded is True
    assert audit.request_id == "req-abc-123"


async def test_plugin_audit_defaults_and_failure_case(
    db_session: AsyncSession, organization_id: uuid.UUID
) -> None:
    audit = PluginAudit(
        organization_id=organization_id,
        action=AuditAction.PLUGIN_REMOVED,
        entity_type="plugin_installation",
        occurred_at=utcnow(),
        summary="Removal failed.",
        succeeded=False,
    )
    db_session.add(audit)
    await db_session.flush()
    await db_session.refresh(audit)
    assert audit.actor_type == "user"
    assert audit.changes == {}
    assert audit.context == {}
    assert audit.entity_id is None
    assert audit.succeeded is False
