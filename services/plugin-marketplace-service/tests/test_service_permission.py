"""Tests for :class:`app.services.permission.PluginPermissionService` --
capability request/grant/deny/revoke for one installed plugin instance.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from shared_core.exceptions.validation import ValidationError

from app.models.enums import PermissionGrantStatus, PluginPermissionCategory
from app.models.installation import PluginInstallation
from app.repositories.installation import PluginInstallationRepository
from app.services.permission import PluginPermissionService


async def _make_installation(
    installations_repo: PluginInstallationRepository,
    make_plugin: Callable[..., Awaitable[Any]],
    organization_id: uuid.UUID,
    slug: str,
) -> PluginInstallation:
    """A real installed-plugin-instance row -- ``PluginPermissionGrant
    .plugin_installation_id`` is a real foreign key, so a grant row can't
    be created against a made-up installation id.
    """
    plugin = await make_plugin(slug=slug)
    return await installations_repo.create(
        PluginInstallation(
            organization_id=organization_id,
            plugin_id=plugin.id,
            installed_version_number="1.0.0",
            installed_at=datetime.now(UTC),
        )
    )


class TestRequest:
    async def test_request_happy_path(
        self,
        permission_service: PluginPermissionService,
        installations_repo: PluginInstallationRepository,
        make_plugin: Callable[..., Awaitable[Any]],
        organization_id: uuid.UUID,
    ) -> None:
        installation = await _make_installation(
            installations_repo, make_plugin, organization_id, "perm-request"
        )

        grant = await permission_service.request(
            organization_id,
            installation.id,
            category=PluginPermissionCategory.INVENTORY,
            scope="hosts/*",
            justification="Needs inventory read access.",
        )

        assert grant.organization_id == organization_id
        assert grant.plugin_installation_id == installation.id
        assert grant.category == PluginPermissionCategory.INVENTORY
        assert grant.scope == "hosts/*"
        assert grant.justification == "Needs inventory read access."
        assert grant.status == PermissionGrantStatus.PENDING
        assert grant.decided_by is None
        assert grant.decided_at is None

    async def test_request_defaults(
        self,
        permission_service: PluginPermissionService,
        installations_repo: PluginInstallationRepository,
        make_plugin: Callable[..., Awaitable[Any]],
        organization_id: uuid.UUID,
    ) -> None:
        installation = await _make_installation(
            installations_repo, make_plugin, organization_id, "perm-request-defaults"
        )

        grant = await permission_service.request(
            organization_id, installation.id, category=PluginPermissionCategory.API
        )

        assert grant.scope is None
        assert grant.justification is None

    async def test_request_duplicate_category_raises(
        self,
        permission_service: PluginPermissionService,
        installations_repo: PluginInstallationRepository,
        make_plugin: Callable[..., Awaitable[Any]],
        organization_id: uuid.UUID,
    ) -> None:
        installation = await _make_installation(
            installations_repo, make_plugin, organization_id, "perm-dup"
        )
        await permission_service.request(
            organization_id, installation.id, category=PluginPermissionCategory.NETWORK
        )

        with pytest.raises(ValidationError, match="already been requested"):
            await permission_service.request(
                organization_id, installation.id, category=PluginPermissionCategory.NETWORK
            )


class TestDecisions:
    async def test_grant_sets_status_and_decision_fields(
        self,
        permission_service: PluginPermissionService,
        installations_repo: PluginInstallationRepository,
        make_plugin: Callable[..., Awaitable[Any]],
        organization_id: uuid.UUID,
    ) -> None:
        installation = await _make_installation(
            installations_repo, make_plugin, organization_id, "perm-grant"
        )
        requested = await permission_service.request(
            organization_id, installation.id, category=PluginPermissionCategory.FILESYSTEM
        )

        granted = await permission_service.grant(requested.id, decided_by="admin-1")

        assert granted.status == PermissionGrantStatus.GRANTED
        assert granted.decided_by == "admin-1"
        assert granted.decided_at is not None

    async def test_deny_sets_status_and_decision_fields(
        self,
        permission_service: PluginPermissionService,
        installations_repo: PluginInstallationRepository,
        make_plugin: Callable[..., Awaitable[Any]],
        organization_id: uuid.UUID,
    ) -> None:
        installation = await _make_installation(
            installations_repo, make_plugin, organization_id, "perm-deny"
        )
        requested = await permission_service.request(
            organization_id, installation.id, category=PluginPermissionCategory.SECRETS
        )

        denied = await permission_service.deny(requested.id, decided_by="admin-2")

        assert denied.status == PermissionGrantStatus.DENIED
        assert denied.decided_by == "admin-2"
        assert denied.decided_at is not None

    async def test_revoke_sets_status_and_decision_fields(
        self,
        permission_service: PluginPermissionService,
        installations_repo: PluginInstallationRepository,
        make_plugin: Callable[..., Awaitable[Any]],
        organization_id: uuid.UUID,
    ) -> None:
        installation = await _make_installation(
            installations_repo, make_plugin, organization_id, "perm-revoke"
        )
        requested = await permission_service.request(
            organization_id, installation.id, category=PluginPermissionCategory.API
        )
        await permission_service.grant(requested.id, decided_by="admin-3")

        revoked = await permission_service.revoke(requested.id, decided_by="admin-4")

        assert revoked.status == PermissionGrantStatus.REVOKED
        assert revoked.decided_by == "admin-4"
        assert revoked.decided_at is not None


class TestListingAndGrantedCategories:
    async def test_list_for_installation_returns_every_status(
        self,
        permission_service: PluginPermissionService,
        installations_repo: PluginInstallationRepository,
        make_plugin: Callable[..., Awaitable[Any]],
        organization_id: uuid.UUID,
    ) -> None:
        installation = await _make_installation(
            installations_repo, make_plugin, organization_id, "perm-list"
        )
        granted_request = await permission_service.request(
            organization_id, installation.id, category=PluginPermissionCategory.MONITORING
        )
        denied_request = await permission_service.request(
            organization_id, installation.id, category=PluginPermissionCategory.NOTIFICATION
        )
        pending_request = await permission_service.request(
            organization_id, installation.id, category=PluginPermissionCategory.CUSTOM
        )
        await permission_service.grant(granted_request.id, decided_by="admin")
        await permission_service.deny(denied_request.id, decided_by="admin")

        grants = await permission_service.list_for_installation(installation.id)

        assert {g.id for g in grants} == {granted_request.id, denied_request.id, pending_request.id}
        statuses = {g.id: g.status for g in grants}
        assert statuses[granted_request.id] == PermissionGrantStatus.GRANTED
        assert statuses[denied_request.id] == PermissionGrantStatus.DENIED
        assert statuses[pending_request.id] == PermissionGrantStatus.PENDING

    async def test_granted_categories_returns_only_currently_granted(
        self,
        permission_service: PluginPermissionService,
        installations_repo: PluginInstallationRepository,
        make_plugin: Callable[..., Awaitable[Any]],
        organization_id: uuid.UUID,
    ) -> None:
        installation = await _make_installation(
            installations_repo, make_plugin, organization_id, "perm-granted-cats"
        )
        workflow_request = await permission_service.request(
            organization_id, installation.id, category=PluginPermissionCategory.WORKFLOW
        )
        automation_request = await permission_service.request(
            organization_id, installation.id, category=PluginPermissionCategory.AUTOMATION
        )
        knowledge_request = await permission_service.request(
            organization_id, installation.id, category=PluginPermissionCategory.KNOWLEDGE_GRAPH
        )

        await permission_service.grant(workflow_request.id, decided_by="admin")
        await permission_service.grant(automation_request.id, decided_by="admin")
        await permission_service.deny(knowledge_request.id, decided_by="admin")
        # A previously-granted capability that is later revoked must drop
        # out of the currently-granted set even though it was granted once.
        await permission_service.revoke(automation_request.id, decided_by="admin")

        categories = await permission_service.granted_categories(installation.id)

        assert categories == frozenset({PluginPermissionCategory.WORKFLOW})
        assert isinstance(categories, frozenset)

    async def test_granted_categories_empty_when_nothing_granted(
        self,
        permission_service: PluginPermissionService,
        installations_repo: PluginInstallationRepository,
        make_plugin: Callable[..., Awaitable[Any]],
        organization_id: uuid.UUID,
    ) -> None:
        installation = await _make_installation(
            installations_repo, make_plugin, organization_id, "perm-none-granted"
        )
        await permission_service.request(
            organization_id, installation.id, category=PluginPermissionCategory.CUSTOM
        )

        categories = await permission_service.granted_categories(installation.id)

        assert categories == frozenset()
