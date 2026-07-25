"""Regression test for the real cross-request persistence bug found during
this service's development: ``get_db_session`` originally never committed
(``BaseRepository`` only ever ``flush()``es), so a user created by one
request was invisible to a different request's own session -- registration
would succeed but a subsequent login would fail with "account not found".
Fixed by routing ``get_db_session`` through
:func:`shared_core.database.session.session_scope`. This test uses
``real_client``/``real_app`` (no DB dependency override) specifically so
each HTTP call gets its own genuine, independently-committed session,
exactly like two unrelated requests from two different clients would.
"""

from __future__ import annotations

from httpx import AsyncClient
from shared_core.database.engine import create_engine
from shared_core.database.session import create_session_factory
from sqlalchemy import delete

from app.models.audit import AuthenticationAuditEntry
from app.models.credentials import UserCredential
from app.models.email_verification import EmailVerificationToken
from app.models.login_history import LoginHistoryEntry
from app.models.password import PasswordHistoryEntry
from app.models.session import Session
from app.models.token import AccessToken, RefreshToken
from app.models.user import User
from tests.conftest import DEFAULT_TEST_PASSWORD, postgres_test_settings, unique_email

_CHILD_TABLES_BY_USER_ID = (
    AccessToken,
    RefreshToken,
    AuthenticationAuditEntry,
    EmailVerificationToken,
    LoginHistoryEntry,
    PasswordHistoryEntry,
    Session,
    UserCredential,
)


async def test_user_registered_in_one_request_is_visible_to_a_later_login_request(
    real_client: AsyncClient,
) -> None:
    email = unique_email()
    try:
        register_response = await real_client.post(
            "/auth/register",
            json={"email": email, "password": DEFAULT_TEST_PASSWORD, "display_name": None},
        )
        assert register_response.status_code == 201

        login_response = await real_client.post(
            "/auth/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD}
        )

        assert login_response.status_code == 200
        assert login_response.json()["data"]["access_token"]
    finally:
        await _delete_real_user(email)


async def _delete_real_user(email: str) -> None:
    """Clean up the row(s) this test committed for real into the shared dev database."""
    engine = create_engine(postgres_test_settings())
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        result = await session.execute(User.__table__.select().where(User.email == email))
        user_row = result.first()
        if user_row is not None:
            user_id = user_row.id
            for model in _CHILD_TABLES_BY_USER_ID:
                await session.execute(delete(model).where(model.user_id == user_id))
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
    await engine.dispose()
