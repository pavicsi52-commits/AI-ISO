"""Construction tests for the request/response schemas backing internal
services that have no dedicated top-level REST endpoint of their own
(baselines, variables, environments, assignments, drift-report/resolve,
policies, approvals, audit, TOSCA, Ansible, Kubernetes) -- docs/039's
own REST list names only the 18 literal endpoints this service's
routers implement; every other service is consumed internally (e.g.
by :class:`~app.services.report.ConfigurationReportService`) or
reserved for a future prompt's own router, the same
"schemas exist ahead of their own router" precedent
``services/asset-management-service``'s own ``test_schemas_unrouted.py``
established.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.enums import (
    ApprovalStatus,
    AuditOutcome,
    BaselineType,
    ChangeSetStatus,
    ConfigurationAssignmentStatus,
    EnvironmentType,
    ManifestFormat,
    PolicyType,
    ToscaComponentType,
    VariableScope,
)
from app.schemas.ansible import (
    ConfigurationAnsibleInventoryCreateRequest,
    ConfigurationAnsibleInventoryResponse,
)
from app.schemas.approval import (
    ConfigurationApprovalCreateRequest,
    ConfigurationApprovalDecisionRequest,
    ConfigurationApprovalResponse,
)
from app.schemas.assignment import (
    ConfigurationAssignmentCreateRequest,
    ConfigurationAssignmentResponse,
)
from app.schemas.audit import ConfigurationAuditResponse
from app.schemas.baseline import (
    ConfigurationBaselineCreateRequest,
    ConfigurationBaselineResponse,
    ConfigurationBaselineUpdateRequest,
)
from app.schemas.change_set import (
    ConfigurationChangeSetCreateRequest,
    ConfigurationChangeSetResponse,
)
from app.schemas.environment import (
    ConfigurationEnvironmentCreateRequest,
    ConfigurationEnvironmentResponse,
    ConfigurationEnvironmentUpdateRequest,
)
from app.schemas.git import ConfigurationGitRepositoryUpdateRequest
from app.schemas.kubernetes import (
    ConfigurationKubernetesManifestCreateRequest,
    ConfigurationKubernetesManifestResponse,
)
from app.schemas.policy import (
    ConfigurationPolicyCreateRequest,
    ConfigurationPolicyResponse,
    ConfigurationPolicyUpdateRequest,
)
from app.schemas.tosca import (
    ConfigurationToscaTemplateCreateRequest,
    ConfigurationToscaTemplateResponse,
)
from app.schemas.variable import (
    ConfigurationVariableCreateRequest,
    ConfigurationVariableResponse,
    ConfigurationVariableUpdateRequest,
)


def test_ansible_schemas() -> None:
    create = ConfigurationAnsibleInventoryCreateRequest(
        organization_id=uuid.uuid4(), name="web-servers"
    )
    assert create.name == "web-servers"

    response = ConfigurationAnsibleInventoryResponse(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        project_id=None,
        profile_id=None,
        name="web-servers",
        inventory_content={},
        host_vars={},
        group_vars={},
        playbooks=[],
        roles=[],
        collections=[],
        vault_ref=None,
    )
    assert response.name == "web-servers"


def test_approval_schemas() -> None:
    create = ConfigurationApprovalCreateRequest(level=2)
    assert create.level == 2

    decision = ConfigurationApprovalDecisionRequest(status=ApprovalStatus.APPROVED)
    assert decision.status == ApprovalStatus.APPROVED

    response = ConfigurationApprovalResponse(
        id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        version_id=None,
        rollback_id=None,
        status=ApprovalStatus.PENDING,
        level=1,
        requested_by=None,
        approver_id=None,
        comments=None,
        decided_at=None,
    )
    assert response.status == ApprovalStatus.PENDING


def test_assignment_schemas() -> None:
    create = ConfigurationAssignmentCreateRequest(managed_asset_id=uuid.uuid4())
    assert create.managed_asset_id

    response = ConfigurationAssignmentResponse(
        id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        managed_asset_id=uuid.uuid4(),
        status=ConfigurationAssignmentStatus.ACTIVE,
        assigned_by=None,
        assigned_at=datetime.now(UTC),
    )
    assert response.status == ConfigurationAssignmentStatus.ACTIVE


def test_audit_response() -> None:
    response = ConfigurationAuditResponse(
        id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        actor_id=None,
        action="create",
        outcome=AuditOutcome.SUCCESS,
        reason="",
        before=None,
        after={"profile_name": "web-tier"},
    )
    assert response.action == "create"


def test_baseline_schemas() -> None:
    create = ConfigurationBaselineCreateRequest(
        organization_id=uuid.uuid4(), baseline_type=BaselineType.GOLDEN_IMAGE, name="rhel9"
    )
    assert create.baseline_type == BaselineType.GOLDEN_IMAGE

    update = ConfigurationBaselineUpdateRequest(name="rhel9", content={"a": 1})
    assert update.content == {"a": 1}

    response = ConfigurationBaselineResponse(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        project_id=None,
        profile_id=None,
        baseline_type=BaselineType.GOLDEN_IMAGE,
        name="rhel9",
        description=None,
        baseline_version="1.0.0",
        content={},
    )
    assert response.baseline_version == "1.0.0"


def test_change_set_schemas() -> None:
    create = ConfigurationChangeSetCreateRequest(changes=[{"key": "port", "value": "8080"}])
    assert create.changes[0]["key"] == "port"

    response = ConfigurationChangeSetResponse(
        id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        status=ChangeSetStatus.DRAFT,
        changes=[],
        applied_at=None,
        created_by=None,
        created_at=datetime.now(UTC),
    )
    assert response.status == ChangeSetStatus.DRAFT


def test_environment_schemas() -> None:
    create = ConfigurationEnvironmentCreateRequest(
        organization_id=uuid.uuid4(), name="staging", environment_type=EnvironmentType.STAGING
    )
    assert create.environment_type == EnvironmentType.STAGING

    update = ConfigurationEnvironmentUpdateRequest(environment_type=EnvironmentType.STAGING)
    assert update.environment_type == EnvironmentType.STAGING

    response = ConfigurationEnvironmentResponse(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        project_id=None,
        name="staging",
        environment_type=EnvironmentType.STAGING,
        description=None,
    )
    assert response.name == "staging"


def test_git_repository_update_schema() -> None:
    update = ConfigurationGitRepositoryUpdateRequest(branch="develop")
    assert update.branch == "develop"


def test_kubernetes_schemas() -> None:
    create = ConfigurationKubernetesManifestCreateRequest(
        organization_id=uuid.uuid4(), format=ManifestFormat.YAML_MANIFEST, name="web"
    )
    assert create.format == ManifestFormat.YAML_MANIFEST

    response = ConfigurationKubernetesManifestResponse(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        project_id=None,
        profile_id=None,
        format=ManifestFormat.YAML_MANIFEST,
        namespace=None,
        name="web",
        content={},
        validated=True,
        validation_errors=None,
    )
    assert response.validated is True


def test_policy_schemas() -> None:
    create = ConfigurationPolicyCreateRequest(
        organization_id=uuid.uuid4(), policy_type=PolicyType.NAMING, name="lowercase-only"
    )
    assert create.policy_type == PolicyType.NAMING

    update = ConfigurationPolicyUpdateRequest(rule={"pattern": "^[a-z]+$"})
    assert update.rule == {"pattern": "^[a-z]+$"}

    response = ConfigurationPolicyResponse(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        project_id=None,
        policy_type=PolicyType.NAMING,
        name="lowercase-only",
        description=None,
        rule={},
        enforced=True,
    )
    assert response.enforced is True


def test_tosca_schemas() -> None:
    create = ConfigurationToscaTemplateCreateRequest(
        organization_id=uuid.uuid4(),
        component_type=ToscaComponentType.NODE_TEMPLATE,
        name="node-a",
    )
    assert create.component_type == ToscaComponentType.NODE_TEMPLATE

    response = ConfigurationToscaTemplateResponse(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        project_id=None,
        profile_id=None,
        component_type=ToscaComponentType.NODE_TEMPLATE,
        name="node-a",
        content={},
        csar_url=None,
    )
    assert response.name == "node-a"


def test_variable_schemas() -> None:
    create = ConfigurationVariableCreateRequest(
        organization_id=uuid.uuid4(), scope=VariableScope.GLOBAL, key="max_connections"
    )
    assert create.key == "max_connections"

    update = ConfigurationVariableUpdateRequest(value="200")
    assert update.value == "200"

    response = ConfigurationVariableResponse(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        project_id=None,
        scope=VariableScope.GLOBAL,
        scope_ref_id=None,
        key="max_connections",
        value="100",
        is_secret_reference=False,
        is_computed=False,
        validation_rule=None,
    )
    assert response.key == "max_connections"
