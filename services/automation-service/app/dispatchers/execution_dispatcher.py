"""Dispatches one automation job's content to the local runner or
remote connector its own :class:`~app.models.enums.PlaybookType` and
(optional) target require.

Per docs/040 "EXECUTION ENGINE"/"CONNECTOR INTEGRATION": a job with no
target runs locally (a real subprocess); a job with an SSH target runs
its content as one real remote command over a live
``shared_core.connectors`` session. Every other
:class:`~app.models.enums.ConnectorType`/unrunnable
:class:`~app.models.enums.PlaybookType` combination raises
:class:`DispatchError` with a clear, honest reason rather than
pretending to execute -- matching
``packages/shared-core/connectors``' own explicit scope note that
concrete provider packages beyond the core SDK (and, here, beyond
SSH) are a separate, later phase of work.
"""

from __future__ import annotations

from shared_core.connectors.connection import ConnectionConfig
from shared_core.connectors.credentials import Credential, ssh_key, username_password
from shared_core.connectors.manager import ConnectorManager

from app.models.automation_target import AutomationTarget
from app.models.enums import ConnectorType, PlaybookType
from app.runners.ansible_runner import run_ansible_playbook
from app.runners.base import RunnerResult
from app.runners.bash_runner import run_bash_script
from app.runners.exceptions import RunnerError
from app.runners.powershell_runner import run_powershell_script
from app.runners.python_runner import run_python_script
from app.runners.shell_runner import run_shell_script
from app.secrets.credential_resolver import SecretCredentialResolver

_LOCAL_RUNNERS = {
    PlaybookType.SHELL_SCRIPT: run_shell_script,
    PlaybookType.BASH: run_bash_script,
    PlaybookType.PYTHON_SCRIPT: run_python_script,
    PlaybookType.POWERSHELL: run_powershell_script,
}

_REMOTE_COMMAND_TYPES = frozenset({PlaybookType.SHELL_SCRIPT, PlaybookType.BASH})
_DEFAULT_LOCAL_ANSIBLE_HOST = "localhost ansible_connection=local"
_PEM_MARKER = "-----BEGIN"


class DispatchError(RunnerError):
    """A job's playbook type/target combination cannot be dispatched."""


def _connector_type_of(target: AutomationTarget) -> ConnectorType:
    """Return a target's connector type as a genuine :class:`ConnectorType`.

    ``AutomationTarget.connector_type`` is annotated
    ``Mapped[ConnectorType]`` but its column is a plain ``String(24)``,
    so SQLAlchemy returns a raw ``str`` for any row loaded from the
    database -- the annotation is a lie MyPy cannot catch. Comparing it
    with ``is`` was therefore ``False`` for *every* stored target, so
    remote dispatch rejected even correctly-configured SSH targets with
    "no concrete provider registered". Normalising first restores the
    check to what it reads as.
    """
    connector_type = target.connector_type
    return (
        connector_type
        if isinstance(connector_type, ConnectorType)
        else ConnectorType(connector_type)
    )


def _build_credential(target: AutomationTarget, secret_value: str | None) -> Credential:
    identity = target.username or "root"
    if secret_value is None:
        return username_password(identity, "")
    if secret_value.lstrip().startswith(_PEM_MARKER):
        return ssh_key(secret_value, identity=identity)
    return username_password(identity, secret_value)


async def _dispatch_remote(
    *,
    playbook_type: PlaybookType,
    content: str,
    target: AutomationTarget,
    connector_manager: ConnectorManager,
    credentials: SecretCredentialResolver,
    caller_token: str,
) -> RunnerResult:
    if _connector_type_of(target) is not ConnectorType.SSH:
        raise DispatchError(
            f"Connector type {target.connector_type!r} has no concrete provider registered "
            "(only SSH is supported by this service)."
        )
    if playbook_type not in _REMOTE_COMMAND_TYPES:
        raise DispatchError(
            f"Playbook type {playbook_type!r} cannot be dispatched to a remote target "
            "directly -- only shell/bash content can."
        )

    secret_value = (
        await credentials.resolve(target.credential_ref, caller_token=caller_token)
        if target.credential_ref is not None
        else None
    )
    credential = _build_credential(target, secret_value)
    config = ConnectionConfig(host=target.address, port=target.port)

    connector = await connector_manager.get_connector("ssh", config, credential)
    try:
        result = await connector.execute(content)
    finally:
        await connector_manager.release_connector("ssh", config, connector)
    return RunnerResult(
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        duration_seconds=result.duration_seconds,
    )


async def dispatch_execution(
    *,
    playbook_type: PlaybookType,
    content: str,
    target: AutomationTarget | None,
    inventory_hosts: list[str] | None = None,
    timeout_seconds: float | None = None,
    connector_manager: ConnectorManager,
    credentials: SecretCredentialResolver,
    caller_token: str,
) -> RunnerResult:
    """Run *content* either locally or against *target*, and return its real result.

    Raises:
        DispatchError: If *playbook_type* has no runner and no target
            dispatch path (``FUTURE_DSL``, ``CUSTOM_PLUGIN``,
            ``WORKFLOW_TASK``, ``TOSCA_SERVICE_TEMPLATE``), *target* is
            given for a *playbook_type* this service can't run
            remotely, or *target*'s own connector type has no concrete
            provider registered.
        RunnerError: If the underlying runner/connector call itself fails.
        DependencyError: If credential resolution against the Secrets
            Management Service fails.
    """
    if target is not None:
        return await _dispatch_remote(
            playbook_type=playbook_type,
            content=content,
            target=target,
            connector_manager=connector_manager,
            credentials=credentials,
            caller_token=caller_token,
        )

    if playbook_type is PlaybookType.ANSIBLE_PLAYBOOK:
        return await run_ansible_playbook(
            content,
            inventory_hosts=inventory_hosts or [_DEFAULT_LOCAL_ANSIBLE_HOST],
            timeout_seconds=timeout_seconds,
        )

    runner = _LOCAL_RUNNERS.get(playbook_type)
    if runner is None:
        raise DispatchError(f"Playbook type {playbook_type!r} has no local runner registered.")
    return await runner(content, timeout_seconds=timeout_seconds)


__all__ = ["DispatchError", "dispatch_execution"]
