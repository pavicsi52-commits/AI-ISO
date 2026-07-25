"""Tests for :mod:`app.dispatchers.execution_dispatcher`.

Local dispatch is exercised via real subprocess runs (matching
``tests/test_runners.py``); remote (SSH) dispatch is exercised against
the same real ``aiios_automation_test_ssh`` Docker container
``tests/test_ssh_connector_live.py`` uses, with credential resolution
mocked at the Secrets Management Service's own documented response
shape via ``pytest-httpx``.
"""

from __future__ import annotations

import socket
import uuid

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.connectors.credentials import CredentialType
from shared_core.connectors.manager import ConnectorManager

from app.connectors.registry import build_connector_registry
from app.dispatchers.execution_dispatcher import (
    DispatchError,
    _build_credential,
    dispatch_execution,
)
from app.models.automation_target import AutomationTarget
from app.models.enums import ConnectorType, ExecutionTargetType, PlaybookType
from app.runners.ansible_runner import is_ansible_available
from app.runners.exceptions import RunnerError
from app.secrets.credential_resolver import SecretCredentialResolver
from tests.conftest import SECRETS_SERVICE_BASE_URL
from tests.test_ssh_connector_live import (
    SSH_TEST_HOST,
    SSH_TEST_PASSWORD,
    SSH_TEST_PORT,
    SSH_TEST_USERNAME,
)


def _ssh_container_reachable() -> bool:
    try:
        with socket.create_connection((SSH_TEST_HOST, SSH_TEST_PORT), timeout=2):
            return True
    except OSError:
        return False


def _ssh_target(*, credential_ref: str | None = None) -> AutomationTarget:
    return AutomationTarget(
        organization_id=uuid.uuid4(),
        name="ssh-target",
        target_type=ExecutionTargetType.PHYSICAL_SERVER,
        connector_type=ConnectorType.SSH,
        address=SSH_TEST_HOST,
        port=SSH_TEST_PORT,
        username=SSH_TEST_USERNAME,
        credential_ref=credential_ref,
    )


class TestBuildCredential:
    def test_plain_password_secret(self) -> None:
        target = _ssh_target()
        credential = _build_credential(target, "s3cr3t")
        assert credential.credential_type == CredentialType.USERNAME_PASSWORD
        assert credential.identity == SSH_TEST_USERNAME
        assert credential.reveal("password") == "s3cr3t"

    def test_pem_secret_builds_ssh_key(self) -> None:
        target = _ssh_target()
        pem = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----"
        credential = _build_credential(target, pem)
        assert credential.credential_type == CredentialType.SSH_KEY
        assert credential.reveal("private_key") == pem

    def test_none_secret_builds_empty_password(self) -> None:
        target = _ssh_target()
        credential = _build_credential(target, None)
        assert credential.credential_type == CredentialType.USERNAME_PASSWORD
        assert credential.reveal("password") == ""

    def test_default_identity_is_root_when_no_username(self) -> None:
        target = _ssh_target()
        target.username = None
        credential = _build_credential(target, "x")
        assert credential.identity == "root"


class TestDispatchExecutionLocal:
    async def test_dispatches_shell_locally(self) -> None:
        result = await dispatch_execution(
            playbook_type=PlaybookType.SHELL_SCRIPT,
            content="echo local-dispatch",
            target=None,
            connector_manager=ConnectorManager(),
            credentials=SecretCredentialResolver(httpx.AsyncClient(), base_url="http://unused"),
            caller_token="tok",
        )
        assert result.succeeded
        assert "local-dispatch" in result.stdout

    async def test_dispatches_python_locally(self) -> None:
        result = await dispatch_execution(
            playbook_type=PlaybookType.PYTHON_SCRIPT,
            content="print('py-dispatch')",
            target=None,
            connector_manager=ConnectorManager(),
            credentials=SecretCredentialResolver(httpx.AsyncClient(), base_url="http://unused"),
            caller_token="tok",
        )
        assert result.succeeded
        assert "py-dispatch" in result.stdout

    async def test_unrunnable_playbook_type_raises_dispatch_error(self) -> None:
        with pytest.raises(DispatchError, match="no local runner registered"):
            await dispatch_execution(
                playbook_type=PlaybookType.FUTURE_DSL,
                content="whatever",
                target=None,
                connector_manager=ConnectorManager(),
                credentials=SecretCredentialResolver(httpx.AsyncClient(), base_url="http://unused"),
                caller_token="tok",
            )

    async def test_ansible_without_target_uses_default_local_host(self) -> None:
        if is_ansible_available():
            pytest.skip("ansible-playbook is installed on this host.")
        with pytest.raises(RunnerError, match="not available on PATH"):
            await dispatch_execution(
                playbook_type=PlaybookType.ANSIBLE_PLAYBOOK,
                content="- hosts: all\n  tasks: []\n",
                target=None,
                connector_manager=ConnectorManager(),
                credentials=SecretCredentialResolver(httpx.AsyncClient(), base_url="http://unused"),
                caller_token="tok",
            )


class TestDispatchExecutionRemote:
    async def test_dispatches_shell_over_ssh(self, httpx_mock: HTTPXMock) -> None:
        if not _ssh_container_reachable():
            pytest.skip("aiios_automation_test_ssh container is not reachable.")
        httpx_mock.add_response(
            url=f"{SECRETS_SERVICE_BASE_URL}/secrets/ssh-secret",
            json={"data": {"value": SSH_TEST_PASSWORD}},
        )
        target = _ssh_target(credential_ref="ssh-secret")
        connector_manager = ConnectorManager(registry=build_connector_registry())
        async with httpx.AsyncClient() as client:
            credentials = SecretCredentialResolver(client, base_url=SECRETS_SERVICE_BASE_URL)
            result = await dispatch_execution(
                playbook_type=PlaybookType.SHELL_SCRIPT,
                content="echo remote-dispatch",
                target=target,
                connector_manager=connector_manager,
                credentials=credentials,
                caller_token="tok",
            )
        assert result.succeeded
        assert "remote-dispatch" in result.stdout
        await connector_manager.close()

    async def test_non_ssh_connector_type_raises_dispatch_error(self) -> None:
        target = _ssh_target()
        target.connector_type = ConnectorType.WINRM
        with pytest.raises(DispatchError, match="no concrete provider registered"):
            await dispatch_execution(
                playbook_type=PlaybookType.SHELL_SCRIPT,
                content="echo hi",
                target=target,
                connector_manager=ConnectorManager(),
                credentials=SecretCredentialResolver(httpx.AsyncClient(), base_url="http://unused"),
                caller_token="tok",
            )

    async def test_unsupported_playbook_type_over_remote_raises_dispatch_error(self) -> None:
        target = _ssh_target()
        with pytest.raises(DispatchError, match="cannot be dispatched to a remote target"):
            await dispatch_execution(
                playbook_type=PlaybookType.PYTHON_SCRIPT,
                content="print('nope')",
                target=target,
                connector_manager=ConnectorManager(registry=build_connector_registry()),
                credentials=SecretCredentialResolver(httpx.AsyncClient(), base_url="http://unused"),
                caller_token="tok",
            )
