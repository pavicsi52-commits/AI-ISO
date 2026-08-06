"""ApiKeyService, ApiKeyRepository, and ApiKeyPermissionRepository.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.

``verify()`` only ever has the raw key a caller presents, never a
``key_id`` -- so it must look up by *hash*, never by id (see
``app/repositories/apikey.py``'s own docstring on ``get_by_hashed_key``).
These tests exercise both directions of rotation (old key stops
verifying, new key starts) and the exact "no restriction" vs
"restricted" boundary for scopes and IP allowlists.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.not_found import NotFoundError

from app.models.apikey import ApiKeyPermission
from app.models.enums import ApiKeyStatus
from app.repositories.apikey import ApiKeyPermissionRepository, ApiKeyRepository
from app.services.apikey import ApiKeyService
from tests.conftest import ago


class TestCreate:
    async def test_creates_with_defaults(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_client
    ) -> None:
        client = await make_client()
        raw_key, created = await api_key_service.create(
            organization_id, client_id=client.id, name="key-1"
        )
        assert isinstance(raw_key, str)
        assert created.name == "key-1"
        assert created.client_id == client.id
        assert created.organization_id == organization_id
        assert created.scopes == []
        assert created.ip_allowlist == []
        assert created.status == ApiKeyStatus.ACTIVE
        assert created.expires_at is None
        assert created.hashed_key != raw_key

    async def test_creates_with_scopes_ttl_and_ip_allowlist(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_client
    ) -> None:
        client = await make_client()
        raw_key, created = await api_key_service.create(
            organization_id,
            client_id=client.id,
            name="key-1",
            scopes=["gateway:read", "gateway:write"],
            ttl_days=7,
            ip_allowlist=["10.0.0.1"],
        )
        # `create_api_key` round-trips scopes through a `frozenset` internally
        # (`ApiKeyRecord.scopes`), so membership -- not list order -- is what's
        # guaranteed here.
        assert set(created.scopes) == {"gateway:read", "gateway:write"}
        assert created.ip_allowlist == ["10.0.0.1"]
        assert created.expires_at is not None
        del raw_key

    async def test_sets_created_by_from_actor_id(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_client
    ) -> None:
        client = await make_client()
        actor_id = uuid.uuid4()
        _raw_key, created = await api_key_service.create(
            organization_id, client_id=client.id, name="key-1", actor_id=str(actor_id)
        )
        assert created.created_by == actor_id

    async def test_the_raw_key_verifies_immediately(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_client
    ) -> None:
        client = await make_client()
        raw_key, created = await api_key_service.create(
            organization_id, client_id=client.id, name="key-1"
        )
        verified = await api_key_service.verify(raw_key)
        assert verified.id == created.id


class TestGet:
    async def test_returns_the_matching_key(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_api_key
    ) -> None:
        _raw_key, created = await make_api_key()
        found = await api_key_service.get(organization_id, created.id)
        assert found.id == created.id

    async def test_raises_not_found_for_a_missing_id(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await api_key_service.get(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, api_key_service: ApiKeyService, make_api_key
    ) -> None:
        _raw_key, created = await make_api_key()
        with pytest.raises(NotFoundError):
            await api_key_service.get(uuid.uuid4(), created.id)


class TestListForClient:
    async def test_lists_every_key_for_the_client(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_client
    ) -> None:
        client = await make_client()
        _rk1, key1 = await api_key_service.create(
            organization_id, client_id=client.id, name="key-1"
        )
        _rk2, key2 = await api_key_service.create(
            organization_id, client_id=client.id, name="key-2"
        )

        found = await api_key_service.list_for_client(organization_id, client.id)
        ids = {one.id for one in found}
        assert {key1.id, key2.id} <= ids

    async def test_scoped_to_client(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_client
    ) -> None:
        client_a = await make_client(name="client-a")
        client_b = await make_client(name="client-b")
        _rk, key_a = await api_key_service.create(
            organization_id, client_id=client_a.id, name="key-a"
        )
        await api_key_service.create(organization_id, client_id=client_b.id, name="key-b")

        found = await api_key_service.list_for_client(organization_id, client_a.id)
        assert [one.id for one in found] == [key_a.id]

    async def test_tenant_isolation(self, api_key_service: ApiKeyService, make_api_key) -> None:
        _raw_key, created = await make_api_key()
        found = await api_key_service.list_for_client(uuid.uuid4(), created.client_id)
        assert found == []


class TestRotate:
    async def test_new_raw_key_differs_from_the_old_one(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_api_key
    ) -> None:
        raw_key, created = await make_api_key()
        new_raw_key, _updated = await api_key_service.rotate(organization_id, created.id)
        assert new_raw_key != raw_key

    async def test_the_old_raw_key_stops_verifying_after_rotation(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_api_key
    ) -> None:
        raw_key, created = await make_api_key()
        await api_key_service.rotate(organization_id, created.id)
        with pytest.raises(AuthenticationError):
            await api_key_service.verify(raw_key)

    async def test_the_new_raw_key_verifies_after_rotation(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_api_key
    ) -> None:
        _raw_key, created = await make_api_key()
        new_raw_key, updated = await api_key_service.rotate(organization_id, created.id)
        verified = await api_key_service.verify(new_raw_key)
        assert verified.id == updated.id

    async def test_preserves_scopes_and_ip_allowlist(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_api_key
    ) -> None:
        _raw_key, created = await make_api_key(scopes=["gateway:read"], ip_allowlist=["10.0.0.1"])
        new_raw_key, updated = await api_key_service.rotate(organization_id, created.id)
        assert updated.scopes == ["gateway:read"]
        assert updated.ip_allowlist == ["10.0.0.1"]
        verified = await api_key_service.verify(new_raw_key, required_scope="gateway:read")
        assert verified.id == updated.id

    async def test_preserves_a_ttl_by_recomputing_expires_at(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_client
    ) -> None:
        client = await make_client()
        _raw_key, created = await api_key_service.create(
            organization_id, client_id=client.id, name="key-1", ttl_days=5
        )
        assert created.expires_at is not None
        _new_raw_key, updated = await api_key_service.rotate(organization_id, created.id)
        assert updated.expires_at is not None

    async def test_leaves_expires_at_none_when_there_was_no_ttl(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_api_key
    ) -> None:
        _raw_key, created = await make_api_key()
        assert created.expires_at is None
        _new_raw_key, updated = await api_key_service.rotate(organization_id, created.id)
        assert updated.expires_at is None

    async def test_reactivates_a_previously_revoked_key(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_api_key
    ) -> None:
        _raw_key, created = await make_api_key()
        await api_key_service.revoke(organization_id, created.id)
        new_raw_key, updated = await api_key_service.rotate(organization_id, created.id)
        assert updated.status == ApiKeyStatus.ACTIVE
        assert updated.revoked_at is None
        verified = await api_key_service.verify(new_raw_key)
        assert verified.id == updated.id

    async def test_sets_updated_by_from_actor_id(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_api_key
    ) -> None:
        _raw_key, created = await make_api_key()
        actor_id = uuid.uuid4()
        _new_raw_key, updated = await api_key_service.rotate(
            organization_id, created.id, actor_id=str(actor_id)
        )
        assert updated.updated_by == actor_id

    async def test_raises_not_found_for_a_missing_id(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await api_key_service.rotate(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, api_key_service: ApiKeyService, make_api_key
    ) -> None:
        _raw_key, created = await make_api_key()
        with pytest.raises(NotFoundError):
            await api_key_service.rotate(uuid.uuid4(), created.id)


class TestRevoke:
    async def test_sets_status_revoked_and_revoked_at(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_api_key
    ) -> None:
        _raw_key, created = await make_api_key()
        revoked = await api_key_service.revoke(organization_id, created.id)
        assert revoked.status == ApiKeyStatus.REVOKED
        assert revoked.revoked_at is not None

    async def test_a_revoked_key_no_longer_verifies(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_api_key
    ) -> None:
        raw_key, created = await make_api_key()
        await api_key_service.revoke(organization_id, created.id)
        with pytest.raises(AuthenticationError):
            await api_key_service.verify(raw_key)

    async def test_sets_updated_by_from_actor_id(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_api_key
    ) -> None:
        _raw_key, created = await make_api_key()
        actor_id = uuid.uuid4()
        revoked = await api_key_service.revoke(organization_id, created.id, actor_id=str(actor_id))
        assert revoked.updated_by == actor_id

    async def test_raises_not_found_for_a_missing_id(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await api_key_service.revoke(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, api_key_service: ApiKeyService, make_api_key
    ) -> None:
        _raw_key, created = await make_api_key()
        with pytest.raises(NotFoundError):
            await api_key_service.revoke(uuid.uuid4(), created.id)


class TestVerify:
    async def test_raises_authentication_error_for_an_unknown_key(
        self, api_key_service: ApiKeyService
    ) -> None:
        with pytest.raises(AuthenticationError):
            await api_key_service.verify("aiios_totally-unknown-key")

    async def test_raises_authentication_error_for_an_expired_key(
        self,
        api_key_service: ApiKeyService,
        api_keys_repo: ApiKeyRepository,
        make_api_key,
    ) -> None:
        raw_key, created = await make_api_key()
        created.expires_at = ago(3600)
        await api_keys_repo.update(created)

        with pytest.raises(AuthenticationError):
            await api_key_service.verify(raw_key)

    async def test_raises_authentication_error_for_a_revoked_key(
        self, api_key_service: ApiKeyService, organization_id: uuid.UUID, make_api_key
    ) -> None:
        raw_key, created = await make_api_key()
        await api_key_service.revoke(organization_id, created.id)
        with pytest.raises(AuthenticationError):
            await api_key_service.verify(raw_key)

    async def test_raises_authentication_error_when_required_scope_is_missing(
        self, api_key_service: ApiKeyService, make_api_key
    ) -> None:
        raw_key, _created = await make_api_key(scopes=["gateway:read"])
        with pytest.raises(AuthenticationError):
            await api_key_service.verify(raw_key, required_scope="gateway:write")

    async def test_succeeds_when_required_scope_is_present(
        self, api_key_service: ApiKeyService, make_api_key
    ) -> None:
        raw_key, created = await make_api_key(scopes=["gateway:read", "gateway:write"])
        verified = await api_key_service.verify(raw_key, required_scope="gateway:read")
        assert verified.id == created.id

    async def test_empty_scopes_means_all_scopes_are_granted(
        self, api_key_service: ApiKeyService, make_api_key
    ) -> None:
        raw_key, created = await make_api_key(scopes=[])
        verified = await api_key_service.verify(raw_key, required_scope="anything:at-all")
        assert verified.id == created.id

    async def test_empty_ip_allowlist_means_no_ip_restriction(
        self, api_key_service: ApiKeyService, make_api_key
    ) -> None:
        raw_key, created = await make_api_key(ip_allowlist=[])
        verified = await api_key_service.verify(raw_key, source_ip="203.0.113.9")
        assert verified.id == created.id

    async def test_succeeds_when_source_ip_is_in_the_allowlist(
        self, api_key_service: ApiKeyService, make_api_key
    ) -> None:
        raw_key, created = await make_api_key(ip_allowlist=["203.0.113.9"])
        verified = await api_key_service.verify(raw_key, source_ip="203.0.113.9")
        assert verified.id == created.id

    async def test_raises_authentication_error_when_source_ip_is_not_in_the_allowlist(
        self, api_key_service: ApiKeyService, make_api_key
    ) -> None:
        raw_key, _created = await make_api_key(ip_allowlist=["203.0.113.9"])
        with pytest.raises(AuthenticationError):
            await api_key_service.verify(raw_key, source_ip="198.51.100.1")

    async def test_ip_check_is_skipped_when_no_source_ip_is_supplied_even_with_an_allowlist(
        self, api_key_service: ApiKeyService, make_api_key
    ) -> None:
        """Documented actual behaviour: the IP-allowlist check only ever runs
        when the caller actually supplies a ``source_ip`` -- an allowlist
        configured on the key does not, by itself, make ``source_ip`` a
        required argument."""
        raw_key, created = await make_api_key(ip_allowlist=["203.0.113.9"])
        verified = await api_key_service.verify(raw_key)
        assert verified.id == created.id

    async def test_updates_last_used_at(self, api_key_service: ApiKeyService, make_api_key) -> None:
        raw_key, created = await make_api_key()
        assert created.last_used_at is None
        verified = await api_key_service.verify(raw_key)
        assert verified.last_used_at is not None


class TestApiKeyRepository:
    """Direct repository-level coverage for paths no service method reaches."""

    async def test_require_in_org_raises_not_found_for_other_org(
        self, api_keys_repo: ApiKeyRepository, make_api_key
    ) -> None:
        _raw_key, created = await make_api_key()
        with pytest.raises(NotFoundError):
            await api_keys_repo.require_in_org(uuid.uuid4(), created.id)

    async def test_get_by_key_id_returns_the_matching_row(
        self, api_keys_repo: ApiKeyRepository, make_api_key
    ) -> None:
        _raw_key, created = await make_api_key()
        found = await api_keys_repo.get_by_key_id(created.key_id)
        assert found is not None
        assert found.id == created.id

    async def test_get_by_key_id_returns_none_for_an_unknown_key_id(
        self, api_keys_repo: ApiKeyRepository
    ) -> None:
        found = await api_keys_repo.get_by_key_id(str(uuid.uuid4()))
        assert found is None

    async def test_get_by_hashed_key_returns_none_for_an_unknown_hash(
        self, api_keys_repo: ApiKeyRepository
    ) -> None:
        found = await api_keys_repo.get_by_hashed_key("not-a-real-hash")
        assert found is None


class TestApiKeyPermissionRepository:
    """No service wraps this repository -- exercised directly."""

    async def test_list_for_key_returns_created_permissions(
        self,
        api_key_permissions_repo: ApiKeyPermissionRepository,
        organization_id: uuid.UUID,
        make_api_key,
    ) -> None:
        _raw_key, created = await make_api_key()
        permission = await api_key_permissions_repo.create(
            ApiKeyPermission(
                organization_id=organization_id,
                api_key_id=created.id,
                resource="orders",
                action="read",
            )
        )
        found = await api_key_permissions_repo.list_for_key(organization_id, created.id)
        assert [p.id for p in found] == [permission.id]

    async def test_returns_empty_list_when_none_exist(
        self,
        api_key_permissions_repo: ApiKeyPermissionRepository,
        organization_id: uuid.UUID,
        make_api_key,
    ) -> None:
        _raw_key, created = await make_api_key()
        found = await api_key_permissions_repo.list_for_key(organization_id, created.id)
        assert found == []

    async def test_tenant_isolation(
        self,
        api_key_permissions_repo: ApiKeyPermissionRepository,
        organization_id: uuid.UUID,
        make_api_key,
    ) -> None:
        _raw_key, created = await make_api_key()
        await api_key_permissions_repo.create(
            ApiKeyPermission(
                organization_id=organization_id,
                api_key_id=created.id,
                resource="orders",
                action="read",
            )
        )
        found = await api_key_permissions_repo.list_for_key(uuid.uuid4(), created.id)
        assert found == []
