"""Ansible inventory structural validation.

Per docs/039 "ANSIBLE INTEGRATION" "Support": Inventories, Host
Variables, Group Variables, Playbooks, Roles, Collections, Vault
References, Execution Metadata. :attr:`ConfigurationAnsibleInventory
.inventory_content` is stored as Ansible's own dynamic-inventory JSON
shape (https://docs.ansible.com/ansible/latest/dev_guide/developing_
inventory.html): a mapping of group name to an object with optional
``hosts``/``vars``/``children`` keys, plus an optional ``_meta.
hostvars`` optimization block -- this module checks that shape without
pulling in ``ansible-core`` itself as a dependency.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_GROUP_KEYS = frozenset({"hosts", "vars", "children"})


class AnsibleValidationError(Exception):
    """An Ansible inventory bundle's content does not match the expected shape."""


def validate_ansible_inventory(
    inventory_content: Mapping[str, Any],
    *,
    host_vars: Mapping[str, Any] | None = None,
    group_vars: Mapping[str, Any] | None = None,
    playbooks: Sequence[str] | None = None,
) -> list[str]:
    """Return every structural problem found across the inventory bundle."""
    errors = _validate_groups(inventory_content)
    errors.extend(_validate_vars("host_vars", host_vars or {}))
    errors.extend(_validate_vars("group_vars", group_vars or {}))
    errors.extend(_validate_playbooks(playbooks or ()))
    return errors


def _validate_groups(inventory_content: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for group_name, group_body in inventory_content.items():
        if group_name == "_meta":
            if not isinstance(group_body, dict) or "hostvars" not in group_body:
                errors.append("group '_meta' must contain a 'hostvars' mapping")
            continue
        if not isinstance(group_body, dict):
            errors.append(f"group {group_name!r} must map to an object")
            continue
        errors.extend(_validate_group_body(group_name, group_body))
    return errors


def _validate_group_body(group_name: str, group_body: Mapping[str, Any]) -> list[str]:
    errors = [
        f"group {group_name!r} has unknown key {key!r}"
        for key in group_body
        if key not in _GROUP_KEYS
    ]
    if "hosts" in group_body and not isinstance(group_body["hosts"], list):
        errors.append(f"group {group_name!r}.hosts must be a list")
    if "children" in group_body and not isinstance(group_body["children"], list):
        errors.append(f"group {group_name!r}.children must be a list")
    if "vars" in group_body and not isinstance(group_body["vars"], dict):
        errors.append(f"group {group_name!r}.vars must be a mapping")
    return errors


def _validate_vars(label: str, vars_by_key: Mapping[str, Any]) -> list[str]:
    return [
        f"{label} for {key!r} must be a mapping"
        for key, value in vars_by_key.items()
        if not isinstance(value, dict)
    ]


def _validate_playbooks(playbooks: Sequence[str]) -> list[str]:
    return [
        f"playbook {playbook!r} must end with .yml or .yaml"
        for playbook in playbooks
        if not playbook.endswith((".yml", ".yaml"))
    ]


def validate_ansible_inventory_or_raise(
    inventory_content: Mapping[str, Any],
    *,
    host_vars: Mapping[str, Any] | None = None,
    group_vars: Mapping[str, Any] | None = None,
    playbooks: Sequence[str] | None = None,
) -> None:
    """Raise :class:`AnsibleValidationError` if the inventory bundle is invalid."""
    errors = validate_ansible_inventory(
        inventory_content, host_vars=host_vars, group_vars=group_vars, playbooks=playbooks
    )
    if errors:
        raise AnsibleValidationError("; ".join(errors))


__all__ = [
    "AnsibleValidationError",
    "validate_ansible_inventory",
    "validate_ansible_inventory_or_raise",
]
