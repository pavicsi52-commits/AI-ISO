"""Tests for :mod:`app.validators.content_validator` -- real parsing/
subprocess checks against the host's own interpreters, no mocking.
"""

from __future__ import annotations

import shutil

import pytest

from app.models.enums import ContentType
from app.validators.content_validator import (
    ContentValidationError,
    validate_content,
    validate_content_or_raise,
)


class TestAnsiblePlaybook:
    async def test_valid_playbook(self) -> None:
        content = "- hosts: all\n  tasks: []\n"
        assert await validate_content(ContentType.ANSIBLE_PLAYBOOK, content) == []

    async def test_import_playbook_is_valid(self) -> None:
        content = "- import_playbook: other.yml\n"
        assert await validate_content(ContentType.ANSIBLE_PLAYBOOK, content) == []

    async def test_missing_hosts_is_invalid(self) -> None:
        errors = await validate_content(ContentType.ANSIBLE_PLAYBOOK, "- tasks: []\n")
        assert errors == ["Play #0 is missing required key(s): hosts"]

    async def test_not_a_list_is_invalid(self) -> None:
        errors = await validate_content(ContentType.ANSIBLE_PLAYBOOK, "hosts: all\n")
        assert "non-empty YAML list" in errors[0]

    async def test_empty_list_is_invalid(self) -> None:
        errors = await validate_content(ContentType.ANSIBLE_PLAYBOOK, "[]\n")
        assert "non-empty YAML list" in errors[0]

    async def test_play_not_a_mapping(self) -> None:
        errors = await validate_content(ContentType.ANSIBLE_PLAYBOOK, "- 'not-a-mapping'\n")
        assert errors == ["Play #0 must be a mapping."]

    async def test_invalid_yaml(self) -> None:
        errors = await validate_content(ContentType.ANSIBLE_PLAYBOOK, "hosts: [unterminated\n")
        assert "Invalid YAML" in errors[0]


class TestAnsibleRole:
    async def test_valid_role(self) -> None:
        content = "- name: install package\n  apt:\n    name: nginx\n"
        assert await validate_content(ContentType.ANSIBLE_ROLE, content) == []

    async def test_not_a_list_is_invalid(self) -> None:
        errors = await validate_content(ContentType.ANSIBLE_ROLE, "name: x\n")
        assert "YAML list of tasks" in errors[0]


class TestAnsibleCollection:
    async def test_valid_collection(self) -> None:
        content = "namespace: myorg\nname: mycollection\n"
        assert await validate_content(ContentType.ANSIBLE_COLLECTION, content) == []

    async def test_missing_keys_is_invalid(self) -> None:
        errors = await validate_content(ContentType.ANSIBLE_COLLECTION, "name: mycollection\n")
        assert "missing required key(s): namespace" in errors[0]


class TestToscaTemplate:
    async def test_valid_template(self) -> None:
        content = "tosca_definitions_version: tosca_simple_yaml_1_3\n"
        assert await validate_content(ContentType.TOSCA_TEMPLATE, content) == []

    async def test_missing_key_is_invalid(self) -> None:
        errors = await validate_content(ContentType.TOSCA_TEMPLATE, "foo: bar\n")
        assert "tosca_definitions_version" in errors[0]


class TestCsarPackage:
    async def test_valid_with_entry_definitions(self) -> None:
        content = "entry_definitions: service.yaml\n"
        assert await validate_content(ContentType.CSAR_PACKAGE, content) == []

    async def test_valid_with_tosca_definitions_version(self) -> None:
        content = "tosca_definitions_version: tosca_simple_yaml_1_3\n"
        assert await validate_content(ContentType.CSAR_PACKAGE, content) == []

    async def test_missing_both_is_invalid(self) -> None:
        errors = await validate_content(ContentType.CSAR_PACKAGE, "foo: bar\n")
        assert "requires either" in errors[0]

    async def test_not_a_mapping_is_invalid(self) -> None:
        errors = await validate_content(ContentType.CSAR_PACKAGE, "- a\n- b\n")
        assert "must be a YAML mapping" in errors[0]


class TestHelmChart:
    async def test_valid_chart(self) -> None:
        content = "apiVersion: v2\nname: mychart\nversion: 1.0.0\n"
        assert await validate_content(ContentType.HELM_CHART, content) == []

    async def test_missing_keys_is_invalid(self) -> None:
        errors = await validate_content(ContentType.HELM_CHART, "name: mychart\n")
        assert "apiVersion" in errors[0]
        assert "version" in errors[0]


class TestKubernetesYaml:
    async def test_valid_single_resource(self) -> None:
        content = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: x\n"
        assert await validate_content(ContentType.KUBERNETES_YAML, content) == []

    async def test_valid_multi_document(self) -> None:
        content = (
            "apiVersion: v1\nkind: Pod\nmetadata:\n  name: a\n"
            "---\n"
            "apiVersion: v1\nkind: Pod\nmetadata:\n  name: b\n"
        )
        assert await validate_content(ContentType.KUBERNETES_YAML, content) == []

    async def test_missing_metadata_name_is_invalid(self) -> None:
        content = "apiVersion: v1\nkind: Pod\nmetadata: {}\n"
        errors = await validate_content(ContentType.KUBERNETES_YAML, content)
        assert "metadata is missing required key: name" in errors[0]

    async def test_missing_required_keys_is_invalid(self) -> None:
        errors = await validate_content(ContentType.KUBERNETES_YAML, "foo: bar\n")
        assert "apiVersion" in errors[0]

    async def test_not_a_mapping_document_is_invalid(self) -> None:
        errors = await validate_content(ContentType.KUBERNETES_YAML, "- a\n- b\n")
        assert "must be a YAML mapping" in errors[0]


class TestWorkflowAndAutomationTemplates:
    async def test_valid_mapping(self) -> None:
        assert await validate_content(ContentType.WORKFLOW_TEMPLATE, "name: x\n") == []
        assert await validate_content(ContentType.AUTOMATION_TEMPLATE, "name: x\n") == []

    async def test_non_mapping_is_invalid(self) -> None:
        errors = await validate_content(ContentType.WORKFLOW_TEMPLATE, "- a\n- b\n")
        assert "YAML mapping" in errors[0]


class TestPythonScript:
    async def test_valid_script(self) -> None:
        assert await validate_content(ContentType.PYTHON_SCRIPT, "print('hi')\n") == []

    async def test_invalid_syntax(self) -> None:
        errors = await validate_content(ContentType.PYTHON_SCRIPT, "def f(:\n    pass\n")
        assert "Python syntax error" in errors[0]


class TestShellAndBashScripts:
    async def test_valid_shell_script(self) -> None:
        assert await validate_content(ContentType.SHELL_SCRIPT, "echo hi\n") == []

    async def test_invalid_shell_script(self) -> None:
        errors = await validate_content(ContentType.SHELL_SCRIPT, "if [ 1 -eq 1\n  echo hi\n")
        assert "sh syntax error" in errors[0]

    async def test_valid_bash_script(self) -> None:
        assert await validate_content(ContentType.BASH_SCRIPT, "echo hi\n") == []

    async def test_invalid_bash_script(self) -> None:
        errors = await validate_content(ContentType.BASH_SCRIPT, "if [ 1 -eq 1\n  echo hi\n")
        assert "bash syntax error" in errors[0]


class TestPowershellScript:
    async def test_powershell_result_is_a_list(self) -> None:
        # Real syntax check when pwsh/powershell.exe is on PATH,
        # honest "not available" message otherwise -- either way, a
        # list of zero or more error strings.
        errors = await validate_content(ContentType.POWERSHELL_SCRIPT, "Write-Output 'hi'\n")
        assert isinstance(errors, list)

    async def test_valid_script_when_powershell_available(self) -> None:
        if shutil.which("pwsh") is None and shutil.which("powershell.exe") is None:
            pytest.skip("Neither pwsh nor powershell.exe is available on PATH.")
        errors = await validate_content(ContentType.POWERSHELL_SCRIPT, "Write-Output 'hi'\n")
        assert errors == []


class TestTerraformAndCustomPlugin:
    async def test_terraform_is_not_yet_supported(self) -> None:
        errors = await validate_content(ContentType.TERRAFORM_MODULE, "anything")
        assert "not yet a supported content type" in errors[0]

    async def test_custom_plugin_always_valid(self) -> None:
        assert await validate_content(ContentType.CUSTOM_PLUGIN, "anything at all") == []


class TestValidateContentOrRaise:
    async def test_raises_on_invalid_content(self) -> None:
        with pytest.raises(ContentValidationError):
            await validate_content_or_raise(ContentType.PYTHON_SCRIPT, "def f(:\n")

    async def test_does_not_raise_on_valid_content(self) -> None:
        await validate_content_or_raise(ContentType.PYTHON_SCRIPT, "print(1)\n")
