"""Construction tests for the request/response schemas backing internal
concerns that have no dedicated top-level REST endpoint of their own
(artifacts, audit, categories, collections, dependencies, labels,
reviews, roles, scripts, signatures, tags, variables) -- docs/041's own
REST list names only the 16 literal endpoints ``app/api``'s six routers
implement; every other schema is consumed internally (e.g. by
:class:`~app.services.dependency.PlaybookDependencyService`) or reserved
for a future prompt's own router, the same "schemas exist ahead of
their own router" precedent ``services/automation-service``'s own
``test_schemas_unrouted.py`` established.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.enums import (
    ArtifactType,
    AuditOutcome,
    ContentType,
    DependencyType,
    ReviewStatus,
    SignatureAlgorithm,
)
from app.schemas.artifact import PlaybookArtifactResponse
from app.schemas.audit import PlaybookAuditResponse
from app.schemas.category import PlaybookCategoryCreateRequest, PlaybookCategoryResponse
from app.schemas.collection import PlaybookCollectionCreateRequest, PlaybookCollectionResponse
from app.schemas.dependency import PlaybookDependencyCreateRequest, PlaybookDependencyResponse
from app.schemas.label import PlaybookLabelCreateRequest, PlaybookLabelResponse
from app.schemas.review import (
    PlaybookReviewCreateRequest,
    PlaybookReviewDecisionRequest,
    PlaybookReviewResponse,
)
from app.schemas.role import PlaybookRoleCreateRequest, PlaybookRoleResponse
from app.schemas.script import PlaybookScriptCreateRequest, PlaybookScriptResponse
from app.schemas.signature import PlaybookSignatureCreateRequest, PlaybookSignatureResponse
from app.schemas.tag import PlaybookTagCreateRequest, PlaybookTagResponse
from app.schemas.variable import PlaybookVariableCreateRequest, PlaybookVariableResponse


def test_artifact_response() -> None:
    response = PlaybookArtifactResponse(
        id=uuid.uuid4(),
        playbook_id=uuid.uuid4(),
        version_id=None,
        artifact_type=ArtifactType.SIGNED_PACKAGE,
        name="bundle.tar",
        content={},
        checksum=None,
    )
    assert response.artifact_type == ArtifactType.SIGNED_PACKAGE


def test_audit_response() -> None:
    response = PlaybookAuditResponse(
        id=uuid.uuid4(),
        playbook_id=uuid.uuid4(),
        actor_id=None,
        action="create",
        outcome=AuditOutcome.SUCCESS,
        reason="",
        before=None,
        after={"name": "deploy-web"},
    )
    assert response.action == "create"


def test_category_schemas() -> None:
    create = PlaybookCategoryCreateRequest(organization_id=uuid.uuid4(), name="networking")
    assert create.name == "networking"

    response = PlaybookCategoryResponse(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), name="networking", description=None
    )
    assert response.name == "networking"


def test_collection_schemas() -> None:
    create = PlaybookCollectionCreateRequest(collection_name="community.general")
    assert create.collection_name == "community.general"

    response = PlaybookCollectionResponse(
        id=uuid.uuid4(),
        playbook_id=uuid.uuid4(),
        collection_name="community.general",
        collection_version="8.0.0",
        source="galaxy",
    )
    assert response.collection_version == "8.0.0"


def test_dependency_schemas() -> None:
    create = PlaybookDependencyCreateRequest(
        dependency_type=DependencyType.PYTHON_PACKAGE, name="requests"
    )
    assert create.dependency_type == DependencyType.PYTHON_PACKAGE

    response = PlaybookDependencyResponse(
        id=uuid.uuid4(),
        playbook_id=uuid.uuid4(),
        dependency_type=DependencyType.PYTHON_PACKAGE,
        name="requests",
        version_constraint=">=2.0",
        resolved=False,
    )
    assert response.resolved is False


def test_label_schemas() -> None:
    create = PlaybookLabelCreateRequest(key="team", value="platform")
    assert create.value == "platform"

    response = PlaybookLabelResponse(
        id=uuid.uuid4(), playbook_id=uuid.uuid4(), key="team", value="platform"
    )
    assert response.key == "team"


def test_review_schemas() -> None:
    create = PlaybookReviewCreateRequest(version_id=None, reviewer_id=uuid.uuid4())
    assert create.version_id is None

    decision = PlaybookReviewDecisionRequest(status=ReviewStatus.COMPLETED)
    assert decision.status == ReviewStatus.COMPLETED

    response = PlaybookReviewResponse(
        id=uuid.uuid4(),
        playbook_id=uuid.uuid4(),
        version_id=None,
        reviewer_id=None,
        status=ReviewStatus.PENDING,
        comments=None,
        reviewed_at=None,
    )
    assert response.status == ReviewStatus.PENDING


def test_role_schemas() -> None:
    create = PlaybookRoleCreateRequest(role_name="geerlingguy.nginx")
    assert create.role_source == "galaxy"

    response = PlaybookRoleResponse(
        id=uuid.uuid4(),
        playbook_id=uuid.uuid4(),
        role_name="geerlingguy.nginx",
        role_source="galaxy",
        role_version="3.1.0",
    )
    assert response.role_version == "3.1.0"


def test_script_schemas() -> None:
    create = PlaybookScriptCreateRequest(
        file_name="helper.py", script_type=ContentType.PYTHON_SCRIPT, content="print('hi')"
    )
    assert create.is_entry_point is False

    response = PlaybookScriptResponse(
        id=uuid.uuid4(),
        playbook_id=uuid.uuid4(),
        file_name="helper.py",
        script_type=ContentType.PYTHON_SCRIPT,
        content="print('hi')",
        is_entry_point=True,
    )
    assert response.is_entry_point is True


def test_signature_schemas() -> None:
    create = PlaybookSignatureCreateRequest(signer_id=uuid.uuid4())
    assert create.signer_id is not None

    response = PlaybookSignatureResponse(
        id=uuid.uuid4(),
        playbook_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        signer_id=None,
        algorithm=SignatureAlgorithm.ED25519,
        public_key_fingerprint="SHA256:abc",
        signature="c2ln",
        checksum="deadbeef",
        verified=True,
        signed_at=datetime.now(UTC),
    )
    assert response.verified is True


def test_tag_schemas() -> None:
    create = PlaybookTagCreateRequest(tag="prod")
    assert create.tag == "prod"

    response = PlaybookTagResponse(id=uuid.uuid4(), playbook_id=uuid.uuid4(), tag="prod")
    assert response.tag == "prod"


def test_variable_schemas() -> None:
    create = PlaybookVariableCreateRequest(name="hostname")
    assert create.required is False

    response = PlaybookVariableResponse(
        id=uuid.uuid4(),
        playbook_id=uuid.uuid4(),
        name="hostname",
        default_value=None,
        required=True,
        runtime=False,
        is_secret_reference=False,
        env_var_name=None,
        validation_rule=None,
        description=None,
    )
    assert response.required is True


__all__: list[str] = []
