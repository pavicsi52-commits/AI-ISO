"""Repository-layer tests: the custom finder/listing methods each repository
adds on top of ``shared_core.database.repository.BaseRepository`` (whose
generic CRUD is already exhaustively covered by shared-core's own suite).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from shared_core.enums.audit_action import AuditAction
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.apikey import ApiKey
from app.models.audit import AuthenticationAuditEntry
from app.models.credentials import UserCredential
from app.models.email_verification import EmailVerificationToken
from app.models.enums import AuthMethod, CredentialType, FailedLoginReason
from app.models.failed_login import FailedLoginEntry
from app.models.login_history import LoginHistoryEntry
from app.models.mfa import MfaDevice
from app.models.password import PasswordHistoryEntry, PasswordResetToken
from app.models.service_account import ServiceAccount
from app.models.session import Session
from app.models.token import AccessToken, RefreshToken
from app.models.trusted_device import TrustedDevice
from app.models.user import User
from app.repositories.apikey import ApiKeyRepository
from app.repositories.audit import AuthenticationAuditRepository
from app.repositories.credentials import UserCredentialRepository
from app.repositories.device import TrustedDeviceRepository
from app.repositories.failed_login import FailedLoginRepository
from app.repositories.login_history import LoginHistoryRepository
from app.repositories.mfa import MfaDeviceRepository
from app.repositories.password import PasswordHistoryRepository, PasswordResetTokenRepository
from app.repositories.service_account import ServiceAccountRepository
from app.repositories.session import SessionRepository
from app.repositories.token import AccessTokenRepository, RefreshTokenRepository
from app.repositories.user import UserRepository
from app.repositories.verification import EmailVerificationTokenRepository


async def _make_user(session: AsyncSession, **overrides: object) -> User:
    values: dict[str, object] = {
        "email": f"user-{uuid.uuid4().hex}@example.com",
        "organization_id": DEFAULT_ORGANIZATION_ID,
    }
    values.update(overrides)
    return await UserRepository(session).create(User(**values))  # type: ignore[arg-type]


async def test_user_repository_get_by_email(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = UserRepository(db_session)

    found = await repo.get_by_email(user.email)
    missing = await repo.get_by_email("nobody@example.com")

    assert found is not None
    assert found.id == user.id
    assert missing is None


async def test_user_repository_get_by_email_excludes_soft_deleted_by_default(
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)
    repo = UserRepository(db_session)
    await repo.delete(user.id)

    assert await repo.get_by_email(user.email) is None
    found = await repo.get_by_email(user.email, include_deleted=True)
    assert found is not None
    assert found.id == user.id


async def test_user_credential_repository_get_for_user(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = UserCredentialRepository(db_session)
    await repo.create(
        UserCredential(
            user_id=user.id, hashed_password="hash", organization_id=DEFAULT_ORGANIZATION_ID
        )
    )

    found = await repo.get_for_user(user.id)
    missing = await repo.get_for_user(uuid.uuid4())

    assert found is not None
    assert found.user_id == user.id
    assert found.credential_type == CredentialType.PASSWORD
    assert missing is None


async def test_session_repository_lookups(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = SessionRepository(db_session)
    now = datetime.now(UTC)
    active = await repo.create(
        Session(
            user_id=user.id,
            session_id=str(uuid.uuid4()),
            last_active_at=now,
            expires_at=now + timedelta(hours=1),
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )
    await repo.create(
        Session(
            user_id=user.id,
            session_id=str(uuid.uuid4()),
            last_active_at=now,
            expires_at=now + timedelta(hours=1),
            revoked_at=now,
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    by_id = await repo.get_by_session_id(active.session_id)
    active_only = await repo.list_active_for_user(user.id)

    assert by_id is not None
    assert by_id.id == active.id
    assert [s.id for s in active_only] == [active.id]


async def test_session_repository_revoke_all_for_user(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = SessionRepository(db_session)
    now = datetime.now(UTC)
    for _ in range(3):
        await repo.create(
            Session(
                user_id=user.id,
                session_id=str(uuid.uuid4()),
                last_active_at=now,
                expires_at=now + timedelta(hours=1),
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )

    revoked_count = await repo.revoke_all_for_user(user.id, reason="test")

    assert revoked_count == 3
    assert await repo.list_active_for_user(user.id) == []


async def test_token_repositories_get_by_jti(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    now = datetime.now(UTC)
    access_repo = AccessTokenRepository(db_session)
    refresh_repo = RefreshTokenRepository(db_session)
    access = await access_repo.create(
        AccessToken(
            user_id=user.id,
            jti=str(uuid.uuid4()),
            issued_at=now,
            expires_at=now + timedelta(minutes=15),
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )
    refresh = await refresh_repo.create(
        RefreshToken(
            user_id=user.id,
            jti=str(uuid.uuid4()),
            token_hash="hash",
            issued_at=now,
            expires_at=now + timedelta(days=7),
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    assert (await access_repo.get_by_jti(access.jti)) is not None
    assert (await access_repo.get_by_jti("missing")) is None
    assert (await refresh_repo.get_by_jti(refresh.jti)) is not None
    assert (await refresh_repo.get_by_jti("missing")) is None


async def test_apikey_repository_lookups(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = ApiKeyRepository(db_session)
    key = await repo.create(
        ApiKey(
            user_id=user.id,
            name="k1",
            key_prefix="aiios_ab",
            hashed_key="hashed-key-value",
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    by_hash = await repo.get_by_hashed_key("hashed-key-value")
    for_user = await repo.list_for_user(user.id)

    assert by_hash is not None
    assert by_hash.id == key.id
    assert [k.id for k in for_user] == [key.id]
    assert await repo.get_by_hashed_key("nope") is None


async def test_mfa_device_repository_lookups(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = MfaDeviceRepository(db_session)
    primary = await repo.create(
        MfaDevice(
            user_id=user.id,
            secret="JBSWY3DPEHPK3PXP",
            is_primary=True,
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    found_primary = await repo.get_primary_for_user(user.id)
    all_devices = await repo.list_for_user(user.id)

    assert found_primary is not None
    assert found_primary.id == primary.id
    assert len(all_devices) == 1


async def test_password_repositories(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    history_repo = PasswordHistoryRepository(db_session)
    reset_repo = PasswordResetTokenRepository(db_session)
    for i in range(3):
        await history_repo.create(
            PasswordHistoryEntry(
                user_id=user.id,
                hashed_password=f"hash-{i}",
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
    reset_token = await reset_repo.create(
        PasswordResetToken(
            user_id=user.id,
            token_hash="reset-hash",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    recent = await history_repo.list_recent_for_user(user.id, limit=2)
    found_reset = await reset_repo.get_by_token_hash("reset-hash")

    assert len(recent) == 2
    assert found_reset is not None
    assert found_reset.id == reset_token.id
    assert await reset_repo.get_by_token_hash("missing") is None


async def test_email_verification_token_repository(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = EmailVerificationTokenRepository(db_session)
    token = await repo.create(
        EmailVerificationToken(
            user_id=user.id,
            email=user.email,
            token_hash="verify-hash",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    found = await repo.get_by_token_hash("verify-hash")

    assert found is not None
    assert found.id == token.id
    assert await repo.get_by_token_hash("missing") is None


async def test_trusted_device_repository(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = TrustedDeviceRepository(db_session)
    device = await repo.create(
        TrustedDevice(
            user_id=user.id,
            device_fingerprint="fp-123",
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    found = await repo.get_by_fingerprint(user.id, "fp-123")
    listed = await repo.list_for_user(user.id)

    assert found is not None
    assert found.id == device.id
    assert [d.id for d in listed] == [device.id]
    assert await repo.get_by_fingerprint(user.id, "missing") is None


async def test_login_history_repository(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = LoginHistoryRepository(db_session)
    for _ in range(2):
        await repo.create(
            LoginHistoryEntry(
                user_id=user.id, method=AuthMethod.PASSWORD, organization_id=DEFAULT_ORGANIZATION_ID
            )
        )

    recent = await repo.list_recent_for_user(user.id, limit=1)

    assert len(recent) == 1


async def test_failed_login_repository_counts_recent(db_session: AsyncSession) -> None:
    repo = FailedLoginRepository(db_session)
    identifier = f"attacker-{uuid.uuid4().hex}@example.com"
    for _ in range(3):
        await repo.create(
            FailedLoginEntry(
                identifier=identifier,
                reason=FailedLoginReason.INVALID_CREDENTIALS,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )

    count = await repo.count_recent_for_identifier(
        identifier, since=datetime.now(UTC) - timedelta(minutes=15)
    )
    count_future = await repo.count_recent_for_identifier(
        identifier, since=datetime.now(UTC) + timedelta(minutes=15)
    )

    assert count == 3
    assert count_future == 0


async def test_authentication_audit_repository(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    repo = AuthenticationAuditRepository(db_session)
    for _ in range(2):
        await repo.create(
            AuthenticationAuditEntry(
                user_id=user.id, action=AuditAction.LOGIN, organization_id=DEFAULT_ORGANIZATION_ID
            )
        )

    recent = await repo.list_recent_for_user(user.id, limit=1)

    assert len(recent) == 1


async def test_service_account_repository(db_session: AsyncSession) -> None:
    repo = ServiceAccountRepository(db_session)
    name = f"svc-{uuid.uuid4().hex}"
    account = await repo.create(
        ServiceAccount(
            name=name,
            hashed_token="hashed-token",
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )

    by_token = await repo.get_by_hashed_token("hashed-token")
    by_name = await repo.get_by_name(name)

    assert by_token is not None
    assert by_token.id == account.id
    assert by_name is not None
    assert by_name.id == account.id
    assert await repo.get_by_hashed_token("missing") is None
    assert await repo.get_by_name("missing") is None
