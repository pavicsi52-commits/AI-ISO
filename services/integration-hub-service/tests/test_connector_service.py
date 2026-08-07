"""ConnectorService and the connector/category/version repositories: registration,
lifecycle transitions, upgrade/rollback version bookkeeping, and category seeding.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from shared_core.plugins.exceptions import VersionIncompatibleError

from app.models.enums import ConnectorAuthMethod, ConnectorCategory, ConnectorLifecycleStatus
from app.repositories.connector import ConnectorCategoryRepository, ConnectorVersionRepository
from app.services.connector import ConnectorService


class TestRegister:
    async def test_creates_with_defaults(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        created = await connector_service.register(
            organization_id, name="aws-connector", category=ConnectorCategory.CLOUD,
            connector_type="aws",
        )
        assert created.name == "aws-connector"
        assert created.category == ConnectorCategory.CLOUD
        assert created.connector_type == "aws"
        assert created.auth_method == ConnectorAuthMethod.API_KEY
        assert created.status == ConnectorLifecycleStatus.REGISTERED
        assert created.description is None
        assert created.owner_id is None
        assert created.marketplace_entry_id is None
        assert created.tags == []
        assert created.config == {}
        assert created.enabled is False
        assert created.consecutive_failures == 0
        assert created.current_version_number is None
        assert created.last_validated_at is None
        assert created.organization_id == organization_id

    async def test_creates_with_custom_fields(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        created = await connector_service.register(
            organization_id,
            name="github-connector",
            category=ConnectorCategory.DEVOPS,
            connector_type="github",
            auth_method=ConnectorAuthMethod.OAUTH2,
            description="GitHub integration",
            owner_id="team-platform",
            tags=["vcs", "ci"],
        )
        assert created.auth_method == ConnectorAuthMethod.OAUTH2
        assert created.description == "GitHub integration"
        assert created.owner_id == "team-platform"
        assert created.tags == ["vcs", "ci"]

    async def test_tags_default_to_an_empty_list_when_none(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        created = await connector_service.register(
            organization_id,
            name="tagless",
            category=ConnectorCategory.CUSTOM,
            connector_type="custom",
            tags=None,
        )
        assert created.tags == []


class TestGet:
    async def test_returns_the_matching_connector(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        found = await connector_service.get(organization_id, created.id)
        assert found.id == created.id

    async def test_raises_not_found_for_a_missing_id(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await connector_service.get(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, connector_service: ConnectorService, make_connector
    ) -> None:
        created = await make_connector()
        with pytest.raises(NotFoundError):
            await connector_service.get(uuid.uuid4(), created.id)


class TestListForOrg:
    async def test_lists_every_connector_in_the_org(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector(name="listed-connector")
        found = await connector_service.list_for_org(organization_id)
        ids = {c.id for c in found}
        assert created.id in ids

    async def test_filters_by_category(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        cloud = await make_connector(name="cloud-one", category=ConnectorCategory.CLOUD)
        storage = await make_connector(name="storage-one", category=ConnectorCategory.STORAGE)
        found = await connector_service.list_for_org(
            organization_id, category=ConnectorCategory.CLOUD
        )
        ids = {c.id for c in found}
        assert cloud.id in ids
        assert storage.id not in ids

    async def test_filters_by_status(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        registered = await make_connector(name="still-registered")
        installed = await make_connector(name="gets-installed")
        await connector_service.install(organization_id, installed.id)

        found = await connector_service.list_for_org(
            organization_id, status=ConnectorLifecycleStatus.INSTALLED
        )
        ids = {c.id for c in found}
        assert installed.id in ids
        assert registered.id not in ids

    async def test_respects_limit_and_offset(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        await make_connector(name="paged-a")
        await make_connector(name="paged-b")
        limited = await connector_service.list_for_org(organization_id, limit=1)
        assert len(limited) == 1

    async def test_tenant_isolation(
        self, connector_service: ConnectorService, make_connector
    ) -> None:
        await make_connector(name="isolated")
        found = await connector_service.list_for_org(uuid.uuid4())
        assert found == []


class TestInstall:
    async def test_moves_to_installed_with_the_default_version(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        installed = await connector_service.install(organization_id, created.id)
        assert installed.status == ConnectorLifecycleStatus.INSTALLED
        assert installed.current_version_number == "1.0.0"

    async def test_installs_a_custom_version(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        installed = await connector_service.install(
            organization_id, created.id, version_number="2.3.1"
        )
        assert installed.current_version_number == "2.3.1"

    async def test_creates_a_current_version_row(
        self,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
        versions_repo: ConnectorVersionRepository,
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="1.0.0")
        history = await versions_repo.list_for_connector(created.id)
        assert len(history) == 1
        assert history[0].version_number == "1.0.0"
        assert history[0].is_current is True
        assert history[0].installed_at is not None

    async def test_snapshots_the_connectors_own_config(
        self,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
        versions_repo: ConnectorVersionRepository,
    ) -> None:
        created = await make_connector()
        await connector_service.configure(
            organization_id, created.id, config={"endpoint_url": "https://example.com"}
        )
        await connector_service.install(organization_id, created.id)
        history = await versions_repo.list_for_connector(created.id)
        assert history[0].config_snapshot == {"endpoint_url": "https://example.com"}

    async def test_rejects_a_malformed_version_string(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        with pytest.raises(VersionIncompatibleError):
            await connector_service.install(
                organization_id, created.id, version_number="not-a-version"
            )

    async def test_raises_not_found_for_a_missing_connector(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await connector_service.install(organization_id, uuid.uuid4())


class TestConfigure:
    async def test_sets_config_and_moves_to_configured(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        updated = await connector_service.configure(
            organization_id, created.id, config={"endpoint_url": "https://example.com"}
        )
        assert updated.config == {"endpoint_url": "https://example.com"}
        assert updated.status == ConnectorLifecycleStatus.CONFIGURED

    async def test_replaces_rather_than_merges_the_previous_config(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        await connector_service.configure(organization_id, created.id, config={"a": 1, "b": 2})
        updated = await connector_service.configure(organization_id, created.id, config={"c": 3})
        assert updated.config == {"c": 3}

    async def test_raises_not_found_for_a_missing_connector(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await connector_service.configure(organization_id, uuid.uuid4(), config={})


class TestMarkValidated:
    async def test_moves_to_validated_and_sets_the_timestamp(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        updated = await connector_service.mark_validated(organization_id, created.id)
        assert updated.status == ConnectorLifecycleStatus.VALIDATED
        assert updated.last_validated_at is not None

    async def test_raises_not_found_for_a_missing_connector(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await connector_service.mark_validated(organization_id, uuid.uuid4())


class TestEnable:
    async def test_enables_and_sets_status(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        updated = await connector_service.enable(organization_id, created.id)
        assert updated.enabled is True
        assert updated.status == ConnectorLifecycleStatus.ENABLED

    async def test_raises_not_found_for_a_missing_connector(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await connector_service.enable(organization_id, uuid.uuid4())


class TestDisable:
    async def test_disables_and_sets_status(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        await connector_service.enable(organization_id, created.id)
        updated = await connector_service.disable(organization_id, created.id)
        assert updated.enabled is False
        assert updated.status == ConnectorLifecycleStatus.DISABLED

    async def test_raises_not_found_for_a_missing_connector(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await connector_service.disable(organization_id, uuid.uuid4())


class TestUpgrade:
    async def test_upgrades_to_a_newer_version(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="1.0.0")
        upgraded = await connector_service.upgrade(
            organization_id, created.id, version_number="1.1.0"
        )
        assert upgraded.current_version_number == "1.1.0"

    async def test_flips_the_old_current_version_row(
        self,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
        versions_repo: ConnectorVersionRepository,
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="1.0.0")
        await connector_service.upgrade(organization_id, created.id, version_number="1.1.0")
        history = {v.version_number: v for v in await versions_repo.list_for_connector(created.id)}
        assert history["1.0.0"].is_current is False
        assert history["1.1.0"].is_current is True

    async def test_creates_a_new_version_row_for_an_unseen_version(
        self,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
        versions_repo: ConnectorVersionRepository,
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="1.0.0")
        await connector_service.upgrade(organization_id, created.id, version_number="2.0.0")
        history = await versions_repo.list_for_connector(created.id)
        assert len(history) == 2

    async def test_reactivates_an_existing_version_row_rather_than_duplicating(
        self,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
        versions_repo: ConnectorVersionRepository,
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="1.0.0")
        await connector_service.upgrade(organization_id, created.id, version_number="2.0.0")
        await connector_service.rollback(organization_id, created.id, version_number="1.0.0")
        await connector_service.upgrade(organization_id, created.id, version_number="2.0.0")

        history = await versions_repo.list_for_connector(created.id)
        assert len(history) == 2  # 2.0.0 reactivated in place, never a third row
        by_version = {v.version_number: v for v in history}
        assert by_version["2.0.0"].is_current is True
        assert by_version["1.0.0"].is_current is False

    async def test_rejects_the_same_version(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="1.0.0")
        with pytest.raises(ValidationError):
            await connector_service.upgrade(organization_id, created.id, version_number="1.0.0")

    async def test_rejects_an_older_version(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="2.0.0")
        with pytest.raises(ValidationError):
            await connector_service.upgrade(organization_id, created.id, version_number="1.0.0")

    async def test_rejects_a_malformed_version_string(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="1.0.0")
        with pytest.raises(VersionIncompatibleError):
            await connector_service.upgrade(
                organization_id, created.id, version_number="not-a-version"
            )

    async def test_succeeds_on_a_never_installed_connector_regardless_of_ordering(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        """No prior ``current_version_number`` means the ordering guard is skipped entirely."""
        created = await make_connector()
        upgraded = await connector_service.upgrade(
            organization_id, created.id, version_number="0.0.1"
        )
        assert upgraded.current_version_number == "0.0.1"

    async def test_raises_not_found_for_a_missing_connector(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await connector_service.upgrade(organization_id, uuid.uuid4(), version_number="1.0.0")


class TestRollback:
    async def test_rolls_back_to_a_previously_installed_version(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="1.0.0")
        await connector_service.upgrade(organization_id, created.id, version_number="2.0.0")
        rolled_back = await connector_service.rollback(
            organization_id, created.id, version_number="1.0.0"
        )
        assert rolled_back.current_version_number == "1.0.0"

    async def test_flips_is_current_on_rollback(
        self,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
        versions_repo: ConnectorVersionRepository,
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="1.0.0")
        await connector_service.upgrade(organization_id, created.id, version_number="2.0.0")
        await connector_service.rollback(organization_id, created.id, version_number="1.0.0")
        history = {v.version_number: v for v in await versions_repo.list_for_connector(created.id)}
        assert history["1.0.0"].is_current is True
        assert history["2.0.0"].is_current is False

    async def test_does_not_create_a_new_row_for_a_reactivated_version(
        self,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        make_connector,
        versions_repo: ConnectorVersionRepository,
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="1.0.0")
        await connector_service.upgrade(organization_id, created.id, version_number="2.0.0")
        await connector_service.rollback(organization_id, created.id, version_number="1.0.0")
        history = await versions_repo.list_for_connector(created.id)
        assert len(history) == 2

    async def test_rejects_a_version_never_installed(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="2.0.0")
        with pytest.raises(ValidationError):
            await connector_service.rollback(organization_id, created.id, version_number="1.0.0")

    async def test_rejects_a_newer_version(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="1.0.0")
        with pytest.raises(ValidationError):
            await connector_service.rollback(organization_id, created.id, version_number="2.0.0")

    async def test_rejects_the_same_version(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="1.0.0")
        with pytest.raises(ValidationError):
            await connector_service.rollback(organization_id, created.id, version_number="1.0.0")

    async def test_rejects_when_the_connector_was_never_installed_at_all(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        with pytest.raises(ValidationError):
            await connector_service.rollback(organization_id, created.id, version_number="1.0.0")

    async def test_rejects_a_malformed_version_string(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="1.0.0")
        with pytest.raises(VersionIncompatibleError):
            await connector_service.rollback(
                organization_id, created.id, version_number="not-a-version"
            )

    async def test_raises_not_found_for_a_missing_connector(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await connector_service.rollback(organization_id, uuid.uuid4(), version_number="1.0.0")


class TestDeprecate:
    async def test_marks_deprecated_and_disables(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        await connector_service.enable(organization_id, created.id)
        updated = await connector_service.deprecate(organization_id, created.id)
        assert updated.status == ConnectorLifecycleStatus.DEPRECATED
        assert updated.enabled is False

    async def test_raises_not_found_for_a_missing_connector(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await connector_service.deprecate(organization_id, uuid.uuid4())


class TestRemove:
    async def test_marks_removed_and_disables(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        await connector_service.enable(organization_id, created.id)
        updated = await connector_service.remove(organization_id, created.id)
        assert updated.status == ConnectorLifecycleStatus.REMOVED
        assert updated.enabled is False

    async def test_raises_not_found_for_a_missing_connector(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await connector_service.remove(organization_id, uuid.uuid4())


class TestListVersions:
    async def test_lists_newest_first(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        await connector_service.install(organization_id, created.id, version_number="1.0.0")
        await connector_service.upgrade(organization_id, created.id, version_number="1.1.0")
        versions = await connector_service.list_versions(organization_id, created.id)
        assert [v.version_number for v in versions] == ["1.1.0", "1.0.0"]

    async def test_empty_before_any_install(
        self, connector_service: ConnectorService, organization_id: uuid.UUID, make_connector
    ) -> None:
        created = await make_connector()
        versions = await connector_service.list_versions(organization_id, created.id)
        assert versions == []

    async def test_raises_not_found_for_a_missing_connector(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await connector_service.list_versions(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_connector(
        self, connector_service: ConnectorService, make_connector
    ) -> None:
        created = await make_connector()
        with pytest.raises(NotFoundError):
            await connector_service.list_versions(uuid.uuid4(), created.id)


class TestRecordHealthOutcome:
    async def test_success_resets_consecutive_failures_and_sets_the_timestamp(
        self, connector_service: ConnectorService, make_connector
    ) -> None:
        created = await make_connector()
        await connector_service.record_health_outcome(created, succeeded=False)
        await connector_service.record_health_outcome(created, succeeded=False)
        assert created.consecutive_failures == 2

        updated = await connector_service.record_health_outcome(created, succeeded=True)
        assert updated.consecutive_failures == 0
        assert updated.last_health_check_at is not None

    async def test_failure_increments_consecutive_failures(
        self, connector_service: ConnectorService, make_connector
    ) -> None:
        created = await make_connector()
        updated = await connector_service.record_health_outcome(created, succeeded=False)
        assert updated.consecutive_failures == 1


class TestEnsureDefaultCategories:
    async def test_seeds_all_fifteen_built_in_categories(
        self,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        categories_repo: ConnectorCategoryRepository,
    ) -> None:
        await connector_service.ensure_default_categories(organization_id)
        rows = await categories_repo.list_for_org(organization_id)
        assert len(rows) == len(ConnectorCategory)
        names = {row.name for row in rows}
        assert names == set(ConnectorCategory)
        assert all(row.built_in for row in rows)

    async def test_is_idempotent_and_creates_zero_new_rows_on_a_second_call(
        self,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        categories_repo: ConnectorCategoryRepository,
    ) -> None:
        await connector_service.ensure_default_categories(organization_id)
        first_ids = {row.id for row in await categories_repo.list_for_org(organization_id)}
        assert len(first_ids) == len(ConnectorCategory)

        await connector_service.ensure_default_categories(organization_id)
        second_ids = {row.id for row in await categories_repo.list_for_org(organization_id)}
        assert second_ids == first_ids  # same rows -- nothing new was created

    async def test_is_scoped_per_organization(
        self,
        connector_service: ConnectorService,
        organization_id: uuid.UUID,
        categories_repo: ConnectorCategoryRepository,
    ) -> None:
        await connector_service.ensure_default_categories(organization_id)
        other_org = uuid.uuid4()
        rows = await categories_repo.list_for_org(other_org)
        assert rows == []


class TestListCategories:
    async def test_returns_the_seeded_categories(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        await connector_service.ensure_default_categories(organization_id)
        rows = await connector_service.list_categories(organization_id)
        assert len(rows) == len(ConnectorCategory)

    async def test_empty_before_seeding(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        rows = await connector_service.list_categories(organization_id)
        assert rows == []

    async def test_tenant_isolation(
        self, connector_service: ConnectorService, organization_id: uuid.UUID
    ) -> None:
        await connector_service.ensure_default_categories(organization_id)
        rows = await connector_service.list_categories(uuid.uuid4())
        assert rows == []
