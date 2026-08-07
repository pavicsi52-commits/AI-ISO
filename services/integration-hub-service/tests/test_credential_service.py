"""CredentialService: assignment, rotation, live/self-managed resolution, expiry.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test, and a
real Starlette-backed Secrets Management Service double (via
``credential_resolver``'s own ``http_client`` fixture and
``httpx.ASGITransport``) for the ``secret_ref``-based resolution paths --
never mocked, per ``tests/conftest.py``'s own docstring.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.connectors.credentials import CredentialType
from shared_core.exceptions.dependency import DependencyError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.config.settings import IntegrationHubServiceSettings
from app.models.enums import CredentialStatus
from app.repositories.credential import ConnectorCredentialRepository
from app.services.credential import CredentialService
from tests.conftest import KNOWN_SECRET_ID, KNOWN_SECRET_VALUE, MISSING_SECRET_ID, ago, soon, utcnow


class TestAssign:
    async def test_raises_when_both_secret_ref_and_raw_value_are_given(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        with pytest.raises(ValidationError):
            await credential_service.assign(
                organization_id,
                connector_id=connector.id,
                credential_type=CredentialType.API_KEY,
                secret_ref="some-secret-id",
                raw_value="some-raw-value",
            )

    async def test_raises_when_neither_secret_ref_nor_raw_value_is_given(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        with pytest.raises(ValidationError):
            await credential_service.assign(
                organization_id, connector_id=connector.id, credential_type=CredentialType.API_KEY
            )

    async def test_a_raw_value_is_encrypted_at_rest(
        self,
        credential_service: CredentialService,
        credentials_repo: ConnectorCredentialRepository,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="super-secret-value",
        )
        assert created.organization_id == organization_id
        assert created.connector_id == connector.id
        assert created.status == CredentialStatus.ACTIVE
        assert created.secret_ref is None
        assert created.encrypted_value is not None
        assert created.encrypted_value != "super-secret-value"
        assert "super-secret-value" not in created.encrypted_value

        raw = await credentials_repo.get_by_id(created.id)
        assert raw is not None
        assert raw.encrypted_value == created.encrypted_value

    async def test_a_secret_ref_stores_only_the_reference_never_a_value(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.OAUTH2,
            secret_ref=KNOWN_SECRET_ID,
        )
        assert created.secret_ref == KNOWN_SECRET_ID
        assert created.encrypted_value is None
        assert created.status == CredentialStatus.ACTIVE

    async def test_assign_stores_the_given_refresh_value_and_expiry(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        expiry = soon(3600)
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.OAUTH2,
            raw_value="access-token-value",
            refresh_value="refresh-token-value",
            expires_at=expiry,
            owner_id="owner-42",
        )
        assert created.expires_at == expiry
        assert created.owner_id == "owner-42"
        assert await credential_service.resolve_refresh_value(created) == "refresh-token-value"


class TestGet:
    async def test_get_returns_the_matching_credential(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="a-secret-value",
        )
        found = await credential_service.get(organization_id, created.id)
        assert found.id == created.id

    async def test_get_raises_not_found_for_a_credential_in_a_different_organization(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="a-secret-value",
        )
        with pytest.raises(NotFoundError):
            await credential_service.get(uuid.uuid4(), created.id)

    async def test_get_raises_not_found_for_an_unknown_id(
        self, credential_service: CredentialService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await credential_service.get(organization_id, uuid.uuid4())


class TestListAndActiveForConnector:
    async def test_list_for_connector_returns_every_assignment_newest_first(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        first = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="first-secret-value",
        )
        second = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="second-secret-value",
        )
        listed = await credential_service.list_for_connector(connector.id)
        assert [c.id for c in listed] == [second.id, first.id]

    async def test_list_for_connector_is_empty_for_a_connector_with_no_credentials(
        self, credential_service: CredentialService, make_connector
    ) -> None:
        connector = await make_connector()
        assert await credential_service.list_for_connector(connector.id) == []

    async def test_get_active_for_connector_returns_the_most_recently_assigned(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="first-secret-value",
        )
        second = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="second-secret-value",
        )
        active = await credential_service.get_active_for_connector(connector.id)
        assert active is not None
        assert active.id == second.id

    async def test_get_active_for_connector_returns_none_when_none_assigned(
        self, credential_service: CredentialService, make_connector
    ) -> None:
        connector = await make_connector()
        assert await credential_service.get_active_for_connector(connector.id) is None

    async def test_get_active_for_connector_ignores_an_expired_credential(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="a-secret-value",
        )
        await credential_service.mark_expired(created)
        assert await credential_service.get_active_for_connector(connector.id) is None


class TestRotate:
    async def test_rotate_replaces_the_encrypted_value(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="original-secret-value",
        )
        # Captured now, as a plain string -- `rotate()` re-fetches `created.id`
        # through the same session's own identity map and mutates that *same*
        # ORM instance in place, so holding onto `created` itself would
        # silently observe the post-rotation state too.
        original_encrypted_value = created.encrypted_value
        rotated = await credential_service.rotate(
            organization_id, created.id, raw_value="rotated-secret-value"
        )
        assert rotated.encrypted_value != original_encrypted_value
        assert await credential_service.resolve_value(rotated) == "rotated-secret-value"

    async def test_rotate_sets_last_rotated_at(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="original-secret-value",
        )
        assert created.last_rotated_at is None
        rotated = await credential_service.rotate(
            organization_id, created.id, raw_value="rotated-secret-value"
        )
        assert rotated.last_rotated_at is not None

    async def test_rotate_resets_status_to_active(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="original-secret-value",
        )
        await credential_service.mark_expired(created)
        rotated = await credential_service.rotate(
            organization_id, created.id, raw_value="rotated-secret-value"
        )
        assert rotated.status == CredentialStatus.ACTIVE

    async def test_rotate_replaces_the_refresh_value_when_given(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.OAUTH2,
            raw_value="access-token-value",
            refresh_value="original-refresh-value",
        )
        rotated = await credential_service.rotate(
            organization_id,
            created.id,
            raw_value="new-access-token-value",
            refresh_value="new-refresh-value",
        )
        assert await credential_service.resolve_refresh_value(rotated) == "new-refresh-value"

    async def test_rotate_leaves_the_refresh_value_untouched_when_not_given(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.OAUTH2,
            raw_value="access-token-value",
            refresh_value="original-refresh-value",
        )
        rotated = await credential_service.rotate(
            organization_id, created.id, raw_value="new-access-token-value"
        )
        assert await credential_service.resolve_refresh_value(rotated) == "original-refresh-value"

    async def test_rotate_with_expires_at_replaces_the_previous_expiry(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="original-secret-value",
            expires_at=soon(3600),
        )
        new_expiry = soon(7200)
        rotated = await credential_service.rotate(
            organization_id, created.id, raw_value="rotated-secret-value", expires_at=new_expiry
        )
        assert rotated.expires_at == new_expiry

    async def test_rotate_without_expires_at_leaves_the_previous_expiry_untouched(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        """Regression test for a genuine bug fixed in
        ``app/services/credential.py``: ``rotate()`` used to
        unconditionally overwrite ``expires_at`` with whatever was
        given (defaulting to ``None``) even when the caller only meant
        to replace the credential's value -- silently erasing any
        previously tracked expiry and dropping the credential out of
        ``list_expiring_before``'s own sweep forever. It now mirrors
        ``refresh_value``'s own "leave alone unless given" handling in
        this exact same method.
        """
        connector = await make_connector()
        expiry = soon(3600)
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="original-secret-value",
            expires_at=expiry,
        )
        rotated = await credential_service.rotate(
            organization_id, created.id, raw_value="rotated-secret-value"
        )
        assert rotated.expires_at == expiry


class TestResolveValue:
    async def test_decrypts_a_self_managed_value(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="self-managed-secret-value",
        )
        assert await credential_service.resolve_value(created) == "self-managed-secret-value"

    async def test_live_resolves_a_known_secret_ref_through_the_injected_resolver(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.OAUTH2,
            secret_ref=KNOWN_SECRET_ID,
        )
        value = await credential_service.resolve_value(created, caller_token="caller-token")
        assert value == KNOWN_SECRET_VALUE

    async def test_a_missing_secret_ref_raises_dependency_error(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.OAUTH2,
            secret_ref=MISSING_SECRET_ID,
        )
        with pytest.raises(DependencyError):
            await credential_service.resolve_value(created, caller_token="caller-token")

    async def test_raises_validation_error_when_no_resolver_is_configured(
        self,
        credentials_repo: ConnectorCredentialRepository,
        service_settings: IntegrationHubServiceSettings,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        service_without_resolver = CredentialService(
            credentials_repo, encryption_key=service_settings.secret_encryption_key, resolver=None
        )
        created = await service_without_resolver.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.OAUTH2,
            secret_ref=KNOWN_SECRET_ID,
        )
        with pytest.raises(ValidationError):
            await service_without_resolver.resolve_value(created)


class TestResolveRefreshValue:
    async def test_returns_none_when_no_refresh_value_is_stored(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="access-only-value",
        )
        assert await credential_service.resolve_refresh_value(created) is None

    async def test_decrypts_the_stored_refresh_value(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.OAUTH2,
            raw_value="access-token-value",
            refresh_value="refresh-token-value",
        )
        assert await credential_service.resolve_refresh_value(created) == "refresh-token-value"


class TestMarkExpired:
    async def test_marks_the_credential_expired(
        self, credential_service: CredentialService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="a-secret-value",
        )
        expired = await credential_service.mark_expired(created)
        assert expired.status == CredentialStatus.EXPIRED


class TestListExpiringBefore:
    async def test_returns_only_active_credentials_whose_expiry_is_past_the_cutoff(
        self, credential_service: CredentialService, make_connector
    ) -> None:
        connector = await make_connector()
        expired_soon = await credential_service.assign(
            connector.organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="past-secret-value",
            expires_at=ago(3600),
        )
        await credential_service.assign(
            connector.organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="future-secret-value",
            expires_at=soon(3600),
        )
        await credential_service.assign(
            connector.organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="no-expiry-secret-value",
        )

        due = await credential_service.list_expiring_before(utcnow())
        assert [c.id for c in due] == [expired_soon.id]

    async def test_excludes_a_credential_that_is_no_longer_active(
        self, credential_service: CredentialService, make_connector
    ) -> None:
        connector = await make_connector()
        created = await credential_service.assign(
            connector.organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="past-secret-value",
            expires_at=ago(3600),
        )
        await credential_service.mark_expired(created)

        assert await credential_service.list_expiring_before(utcnow()) == []

    async def test_respects_the_limit(
        self, credential_service: CredentialService, make_connector
    ) -> None:
        connector = await make_connector()
        await credential_service.assign(
            connector.organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="first-past-secret-value",
            expires_at=ago(3600),
        )
        await credential_service.assign(
            connector.organization_id,
            connector_id=connector.id,
            credential_type=CredentialType.API_KEY,
            raw_value="second-past-secret-value",
            expires_at=ago(1800),
        )
        due = await credential_service.list_expiring_before(utcnow(), limit=1)
        assert len(due) == 1
