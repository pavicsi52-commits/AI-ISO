"""Tests for connection.py, session.py, and credentials.py."""

from __future__ import annotations

from datetime import timedelta

import pytest
from shared_core.connectors.connection import ConnectionConfig, ConnectionState
from shared_core.connectors.credentials import (
    Credential,
    CredentialType,
    api_key,
    bearer_token,
    certificate,
    jwt_credential,
    oauth2_credential,
    ssh_key,
    username_password,
)
from shared_core.connectors.session import Session, new_session_id

# --- connection.py ---


def test_connection_config_defaults() -> None:
    config = ConnectionConfig(host="10.0.0.1")

    assert config.port is None
    assert config.verify_certificates is True
    assert config.use_tls is False


def test_connection_state_covers_the_documented_lifecycle() -> None:
    expected = {"disconnected", "connecting", "connected", "reconnecting", "failed"}
    assert {state.value for state in ConnectionState} == expected


# --- session.py ---


def test_new_session_id_generates_unique_ids() -> None:
    assert new_session_id() != new_session_id()


def test_session_touch_updates_last_used_at() -> None:
    session = Session()
    original = session.last_used_at

    session.touch()

    assert session.last_used_at >= original


def test_session_is_idle_expired_false_when_recently_used() -> None:
    session = Session(idle_timeout_seconds=60)

    assert session.is_idle_expired(now=session.last_used_at) is False


def test_session_is_idle_expired_true_after_the_timeout() -> None:
    session = Session(idle_timeout_seconds=60)
    later = session.last_used_at + timedelta(seconds=61)

    assert session.is_idle_expired(now=later) is True


def test_session_is_lifetime_expired_true_after_max_lifetime() -> None:
    session = Session(max_lifetime_seconds=3600)
    later = session.created_at + timedelta(hours=2)

    assert session.is_lifetime_expired(now=later) is True


def test_session_is_expired_true_when_terminated() -> None:
    session = Session()
    session.terminate()

    assert session.is_expired() is True


def test_session_is_expired_false_for_a_fresh_session() -> None:
    session = Session(idle_timeout_seconds=3600, max_lifetime_seconds=3600)

    assert session.is_expired(now=session.created_at) is False


# --- credentials.py ---


def test_credential_repr_masks_secrets() -> None:
    credential = username_password("admin", "hunter2")

    text = repr(credential)

    assert "hunter2" not in text
    assert "***" in text


def test_credential_str_also_masks_secrets() -> None:
    credential = api_key("sk-live-12345")

    assert "sk-live-12345" not in str(credential)


def test_credential_reveal_returns_the_actual_secret() -> None:
    credential = username_password("admin", "hunter2")

    assert credential.reveal("password") == "hunter2"


def test_credential_reveal_raises_for_an_unknown_key() -> None:
    credential = api_key("sk-live-12345")

    with pytest.raises(KeyError):
        credential.reveal("password")


def test_credential_has_secret() -> None:
    credential = bearer_token("tok-abc")

    assert credential.has_secret("token") is True
    assert credential.has_secret("password") is False


def test_username_password_builds_the_expected_credential() -> None:
    credential = username_password("admin", "hunter2")

    assert credential.credential_type == CredentialType.USERNAME_PASSWORD
    assert credential.identity == "admin"


def test_api_key_builds_the_expected_credential() -> None:
    credential = api_key("sk-live-12345", identity="service-a")

    assert credential.credential_type == CredentialType.API_KEY
    assert credential.reveal("api_key") == "sk-live-12345"


def test_bearer_token_builds_the_expected_credential() -> None:
    credential = bearer_token("tok-abc")

    assert credential.credential_type == CredentialType.BEARER_TOKEN
    assert credential.reveal("token") == "tok-abc"


def test_jwt_credential_builds_the_expected_credential() -> None:
    credential = jwt_credential("eyJhbGci")

    assert credential.credential_type == CredentialType.JWT
    assert credential.reveal("token") == "eyJhbGci"


def test_ssh_key_without_a_passphrase() -> None:
    credential = ssh_key("-----BEGIN KEY-----", identity="deploy")

    assert credential.credential_type == CredentialType.SSH_KEY
    assert credential.has_secret("passphrase") is False


def test_ssh_key_with_a_passphrase() -> None:
    credential = ssh_key("-----BEGIN KEY-----", passphrase="s3cret")

    assert credential.reveal("passphrase") == "s3cret"


def test_certificate_builds_the_expected_credential() -> None:
    credential = certificate("-----BEGIN CERT-----", "-----BEGIN KEY-----")

    assert credential.credential_type == CredentialType.CERTIFICATE
    assert credential.has_secret("certificate")
    assert credential.has_secret("private_key")


def test_oauth2_credential_without_a_refresh_token() -> None:
    credential = oauth2_credential("access-123")

    assert credential.credential_type == CredentialType.OAUTH2
    assert credential.has_secret("refresh_token") is False


def test_oauth2_credential_with_a_refresh_token() -> None:
    credential = oauth2_credential("access-123", refresh_token="refresh-456")

    assert credential.reveal("refresh_token") == "refresh-456"


def test_credential_type_covers_every_documented_type() -> None:
    expected = {
        "username_password",
        "ssh_key",
        "api_key",
        "oauth2",
        "jwt",
        "bearer_token",
        "kerberos",
        "certificate",
        "sso",
    }
    assert {credential_type.value for credential_type in CredentialType} == expected


def test_credential_metadata_defaults_to_empty() -> None:
    credential = Credential(credential_type=CredentialType.API_KEY)

    assert credential.metadata == {}
    assert credential.secrets == {}
