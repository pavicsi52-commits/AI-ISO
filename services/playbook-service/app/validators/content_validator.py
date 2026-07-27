"""Structural content validation, per docs/041 "VALIDATION" "Support":
YAML Validation, JSON Schema Validation, Syntax Validation, Ansible
Lint, Python Lint, PowerShell Validation, Bash Validation, TOSCA
Validation, Helm Validation, Manifest Validation, Dependency
Validation, Metadata Validation.

Docs/041's own "DO NOT IMPLEMENT" section also names "Validation
Engine" -- read alongside this section's own explicit "Support" list,
the "✓ Validation Engine" line in ACCEPTANCE CRITERIA, and "Generate
validation engine" in OUTPUT, the same internal-contradiction shape
every prior AI-IOS prompt in this cluster resolved identically: a real,
*structural* (parse-and-check-shape) validator, never one that
executes untrusted content -- content *execution* is
``services/automation-service``'s own concern (also separately listed
in "DO NOT IMPLEMENT" as "Automation Execution"), not this service's.
The one genuine exception is Python/Bash/Shell/PowerShell "syntax
validation", which for every one of those languages means asking that
language's own real parser to check the source *without running it* --
``ast.parse`` for Python (never ``exec``/``eval``), and ``bash -n``/
``sh -n``/PowerShell's own AST parser for the shell languages (a real,
well-established "check syntax, don't run" flag/API for each,
matching the same "invoke the real interpreter's own parser, never a
hand-rolled one" precedent ``services/automation-service``'s own
runners already established for *execution*).

YAML-shaped content types are checked against the minimum key shape
each format's own specification requires, the same
``_require_keys``-based precedent
``services/configuration-management-service``'s own
``app/tosca/validator.py``/``app/kubernetes/validator.py`` already
established -- no full Ansible-lint/Helm/TOSCA parser dependency.
"""

from __future__ import annotations

import ast
import asyncio
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from app.models.enums import ContentType

_YAML_CONTENT_TYPES = frozenset(
    {
        ContentType.ANSIBLE_PLAYBOOK,
        ContentType.ANSIBLE_ROLE,
        ContentType.ANSIBLE_COLLECTION,
        ContentType.TOSCA_TEMPLATE,
        ContentType.CSAR_PACKAGE,
        ContentType.HELM_CHART,
        ContentType.KUBERNETES_YAML,
        ContentType.WORKFLOW_TEMPLATE,
        ContentType.AUTOMATION_TEMPLATE,
    }
)


class ContentValidationError(Exception):
    """A playbook's content does not match its declared content type."""


async def validate_content(content_type: ContentType, content: str) -> list[str]:
    """Return every structural problem found in *content*; empty if valid."""
    if content_type in _YAML_CONTENT_TYPES:
        return _validate_yaml_content(content_type, content)
    if content_type is ContentType.PYTHON_SCRIPT:
        return _validate_python(content)
    if content_type in (ContentType.SHELL_SCRIPT, ContentType.BASH_SCRIPT):
        return await _validate_shell(content_type, content)
    if content_type is ContentType.POWERSHELL_SCRIPT:
        return await _validate_powershell(content)
    if content_type is ContentType.TERRAFORM_MODULE:
        return ["Terraform Modules are not yet a supported content type (docs/041: '(future)')."]
    # CUSTOM_PLUGIN: no structure is defined anywhere in docs/041 for
    # opaque plugin content -- honestly always structurally valid,
    # rather than inventing a shape no spec names.
    return []


async def validate_content_or_raise(content_type: ContentType, content: str) -> None:
    """Raise :class:`ContentValidationError` if *content* is structurally invalid."""
    errors = await validate_content(content_type, content)
    if errors:
        raise ContentValidationError("; ".join(errors))


def _require_keys(document: Any, label: str, *keys: str) -> list[str]:
    if not isinstance(document, dict):
        return [f"{label} content must be a YAML mapping."]
    missing = [key for key in keys if key not in document]
    if not missing:
        return []
    return [f"{label} is missing required key(s): {', '.join(missing)}"]


def _validate_ansible_playbook(document: Any) -> list[str]:
    if not isinstance(document, list) or not document:
        return ["Ansible playbook content must be a non-empty YAML list of plays."]
    errors: list[str] = []
    for index, play in enumerate(document):
        if not isinstance(play, dict):
            errors.append(f"Play #{index} must be a mapping.")
        elif "hosts" not in play and "import_playbook" not in play:
            errors.append(f"Play #{index} is missing required key(s): hosts")
    return errors


def _validate_ansible_role(document: Any) -> list[str]:
    if not isinstance(document, list):
        return ["Ansible role task content must be a YAML list of tasks."]
    return []


def _validate_csar(document: Any) -> list[str]:
    if not isinstance(document, dict):
        return ["CSAR package content must be a YAML mapping."]
    if "entry_definitions" not in document and "tosca_definitions_version" not in document:
        return [
            "csar_package requires either 'entry_definitions' (TOSCA.meta pointer) "
            "or 'tosca_definitions_version'"
        ]
    return []


def _validate_template_mapping(document: Any) -> list[str]:
    # WORKFLOW_TEMPLATE / AUTOMATION_TEMPLATE: no dedicated shape is
    # defined by docs/041 -- a minimal "parses to a mapping" sanity
    # check, documented as the honest scope of what's actually checked.
    if not isinstance(document, dict):
        return ["Template content must be a YAML mapping at the top level."]
    return []


def _validate_kubernetes_resource(document: Any) -> list[str]:
    if not isinstance(document, dict):
        return ["Kubernetes resource content must be a YAML mapping."]
    errors = _require_keys(document, "Kubernetes resource", "apiVersion", "kind", "metadata")
    metadata = document.get("metadata")
    if isinstance(metadata, dict) and "name" not in metadata:
        errors.append("Kubernetes resource metadata is missing required key: name")
    return errors


_SINGLE_DOCUMENT_VALIDATORS: dict[ContentType, Callable[[Any], list[str]]] = {
    ContentType.ANSIBLE_PLAYBOOK: _validate_ansible_playbook,
    ContentType.ANSIBLE_ROLE: _validate_ansible_role,
    ContentType.ANSIBLE_COLLECTION: lambda doc: _require_keys(
        doc, "Ansible collection galaxy.yml", "namespace", "name"
    ),
    ContentType.TOSCA_TEMPLATE: lambda doc: _require_keys(
        doc, "TOSCA template", "tosca_definitions_version"
    ),
    ContentType.CSAR_PACKAGE: _validate_csar,
    ContentType.HELM_CHART: lambda doc: _require_keys(
        doc, "Helm chart", "apiVersion", "name", "version"
    ),
    ContentType.WORKFLOW_TEMPLATE: _validate_template_mapping,
    ContentType.AUTOMATION_TEMPLATE: _validate_template_mapping,
}


def _validate_yaml_content(content_type: ContentType, content: str) -> list[str]:
    try:
        if content_type is ContentType.KUBERNETES_YAML:
            documents = [doc for doc in yaml.safe_load_all(content) if doc is not None]
        else:
            documents = [yaml.safe_load(content)]
    except yaml.YAMLError as exc:
        return [f"Invalid YAML: {exc}"]

    if content_type is ContentType.KUBERNETES_YAML:
        errors: list[str] = []
        for document in documents:
            errors.extend(_validate_kubernetes_resource(document))
        return errors
    return _SINGLE_DOCUMENT_VALIDATORS[content_type](documents[0])


def _validate_python(content: str) -> list[str]:
    try:
        ast.parse(content)
    except SyntaxError as exc:
        return [f"Python syntax error: {exc.msg} (line {exc.lineno})"]
    return []


async def _validate_shell(content_type: ContentType, content: str) -> list[str]:
    interpreter = "bash" if content_type is ContentType.BASH_SCRIPT else "sh"
    if shutil.which(interpreter) is None:
        return [f"'{interpreter}' is not available on PATH to syntax-check this content."]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as handle:
        handle.write(content)
        script_path = Path(handle.name)
    try:
        process = await asyncio.create_subprocess_exec(
            interpreter,
            "-n",
            str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout_bytes, stderr_bytes = await process.communicate()
    finally:
        await asyncio.to_thread(script_path.unlink, missing_ok=True)

    if process.returncode != 0:
        return [f"{interpreter} syntax error: {stderr_bytes.decode('utf-8', errors='replace')}"]
    return []


def _resolve_powershell_argv() -> list[str] | None:
    if shutil.which("pwsh") is not None:
        return ["pwsh", "-NoProfile", "-NonInteractive", "-Command"]
    if shutil.which("powershell.exe") is not None:
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"]
    return None


async def _validate_powershell(content: str) -> list[str]:
    argv = _resolve_powershell_argv()
    if argv is None:
        return [
            "Neither 'pwsh' nor 'powershell.exe' is available on PATH "
            "to syntax-check this content."
        ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False) as handle:
        handle.write(content)
        script_path = Path(handle.name)
    try:
        parse_command = (
            f"$errors = $null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile("
            f"'{script_path}', [ref]$null, [ref]$errors) | Out-Null; "
            f"if ($errors.Count -gt 0) {{ $errors | ForEach-Object {{ Write-Error $_ }}; exit 1 }}"
        )
        process = await asyncio.create_subprocess_exec(
            *argv,
            parse_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout_bytes, stderr_bytes = await process.communicate()
    finally:
        await asyncio.to_thread(script_path.unlink, missing_ok=True)

    if process.returncode != 0:
        message = stderr_bytes.decode("utf-8", errors="replace").strip() or "syntax error"
        return [f"PowerShell syntax error: {message}"]
    return []


__all__ = ["ContentValidationError", "validate_content", "validate_content_or_raise"]
