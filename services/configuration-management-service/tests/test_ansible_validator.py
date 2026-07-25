"""Tests for :mod:`app.ansible.validator`."""

from __future__ import annotations

import pytest

from app.ansible.validator import (
    AnsibleValidationError,
    validate_ansible_inventory,
    validate_ansible_inventory_or_raise,
)


def test_valid_inventory_has_no_errors() -> None:
    errors = validate_ansible_inventory(
        {
            "webservers": {"hosts": ["web1", "web2"], "vars": {"http_port": 80}},
            "dbservers": {"hosts": ["db1"], "children": []},
            "_meta": {"hostvars": {"web1": {"ansible_user": "deploy"}}},
        },
        host_vars={"web1": {"ansible_user": "deploy"}},
        group_vars={"webservers": {"http_port": 80}},
        playbooks=["site.yml", "deploy.yaml"],
    )
    assert errors == []


def test_meta_group_without_hostvars_is_invalid() -> None:
    errors = validate_ansible_inventory({"_meta": {}})
    assert any("hostvars" in error for error in errors)


def test_group_body_not_a_mapping_is_invalid() -> None:
    errors = validate_ansible_inventory({"webservers": ["web1"]})
    assert any("must map to an object" in error for error in errors)


def test_unknown_group_key_is_invalid() -> None:
    errors = validate_ansible_inventory({"webservers": {"unexpected": True}})
    assert any("unknown key" in error for error in errors)


def test_hosts_not_a_list_is_invalid() -> None:
    errors = validate_ansible_inventory({"webservers": {"hosts": "web1"}})
    assert any("hosts must be a list" in error for error in errors)


def test_children_not_a_list_is_invalid() -> None:
    errors = validate_ansible_inventory({"webservers": {"children": "dbservers"}})
    assert any("children must be a list" in error for error in errors)


def test_vars_not_a_mapping_is_invalid() -> None:
    errors = validate_ansible_inventory({"webservers": {"vars": "http_port=80"}})
    assert any("vars must be a mapping" in error for error in errors)


def test_host_vars_not_a_mapping_is_invalid() -> None:
    errors = validate_ansible_inventory({}, host_vars={"web1": "not-a-mapping"})
    assert any("host_vars" in error for error in errors)


def test_group_vars_not_a_mapping_is_invalid() -> None:
    errors = validate_ansible_inventory({}, group_vars={"webservers": "not-a-mapping"})
    assert any("group_vars" in error for error in errors)


def test_playbook_without_yaml_extension_is_invalid() -> None:
    errors = validate_ansible_inventory({}, playbooks=["site.txt"])
    assert any("must end with .yml or .yaml" in error for error in errors)


def test_validate_or_raise_passes_through_valid_inventory() -> None:
    validate_ansible_inventory_or_raise({"webservers": {"hosts": ["web1"]}})


def test_validate_or_raise_raises_on_invalid_inventory() -> None:
    with pytest.raises(AnsibleValidationError):
        validate_ansible_inventory_or_raise({"webservers": ["not-an-object"]})
