"""Tests for :class:`app.services.discovery_execution.DiscoveryExecutionService`
against a real (SAVEPOINT-isolated) Postgres session, with the
protocol-scanner/enumeration-provider registry and the Secrets
Management/Inventory Service HTTP calls mocked -- ``tests/test_workers.py``
already covers the one fully-real, no-mocking end-to-end path (a real
``TcpScanner`` probe against the docker-compose Redis container); this
file covers every other branch this orchestrator has: rule filtering,
rule-driven classification, credential resolution, cloud/Kubernetes
enumeration (including relationship inference), and event publishing.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from pytest_httpx import HTTPXMock
from shared_core.enums.job_status import JobStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_credential import DiscoveryCredential
from app.models.discovery_job import DiscoveryJob
from app.models.enums import (
    AssetClassification,
    CredentialType,
    DiscoveryMode,
    DiscoveryRelationshipType,
    DiscoveryResultStatus,
    FailureReason,
    ProtocolType,
    RuleType,
    TargetType,
)
from app.repositories.discovery_credential import DiscoveryCredentialRepository
from app.repositories.discovery_job import DiscoveryJobRepository
from app.repositories.discovery_rule import DiscoveryRuleRepository
from app.repositories.discovery_target import DiscoveryTargetRepository
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome
from app.scanners.enumeration import DiscoveredResource, EnumerationError, EnumerationProvider
from app.services import discovery_execution as execution_module
from app.services.job import DiscoveryJobService
from app.services.rule import DiscoveryRuleService
from app.services.target import DiscoveryTargetService
from tests.conftest import (
    INVENTORY_SERVICE_BASE_URL,
    SECRETS_SERVICE_BASE_URL,
    build_execution_service,
    seed_profile,
)

_TIMEOUT_SECONDS = 5.0


class _FakeScanner(ProtocolScanner):
    protocol = ProtocolType.TCP

    def __init__(self, outcome: ScanOutcome) -> None:
        self._outcome = outcome
        self.received_credential: ScanCredential | None = None

    async def probe(
        self, address: str, *, port: int | None, timeout_seconds: float, credential: Any
    ) -> ScanOutcome:
        self.received_credential = credential
        return self._outcome


class _FakeEnumerationProvider(EnumerationProvider):
    target_type = TargetType.CLOUD_ACCOUNT

    def __init__(
        self,
        resources: list[DiscoveredResource] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._resources = resources or []
        self._error = error

    async def enumerate(
        self, address: str, *, credential: Any, timeout_seconds: float
    ) -> list[DiscoveredResource]:
        if self._error is not None:
            raise self._error
        return self._resources


async def _seed_job_with_target(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    target_type: TargetType = TargetType.HOST,
    protocol: ProtocolType = ProtocolType.TCP,
    address: str = "192.0.2.10",
    credential_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> DiscoveryJob:
    profile = await seed_profile(db_session, organization_id=organization_id)
    targets = DiscoveryTargetService(DiscoveryTargetRepository(db_session))
    await targets.create(
        organization_id=organization_id,
        profile_id=profile.id,
        target_type=target_type,
        address=address,
        protocol=protocol,
        credential_id=credential_id,
        metadata=metadata,
    )
    jobs = DiscoveryJobService(
        DiscoveryJobRepository(db_session), DiscoveryTargetRepository(db_session), db_session
    )
    return await jobs.create_job(
        organization_id=organization_id,
        profile_id=profile.id,
        mode=DiscoveryMode.MANUAL,
        triggered_by=None,
    )


async def test_run_job_publishes_started_and_completed_events(
    db_session: AsyncSession, real_http_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = uuid.uuid4()
    job = await _seed_job_with_target(db_session, organization_id=org_id)
    fake_scanner = _FakeScanner(ScanOutcome(status=DiscoveryResultStatus.SUCCESS))
    monkeypatch.setattr(execution_module, "get_scanner", lambda protocol: fake_scanner)

    published: list[object] = []

    async def _publish(event: object) -> None:
        published.append(event)

    service = build_execution_service(db_session, real_http_client, publish_event=_publish)
    result = await service.run_job(job.id, caller_token=None)

    assert result.status == JobStatus.COMPLETED
    event_names = [type(event).__name__ for event in published]
    assert "DiscoveryStartedEvent" in event_names
    assert "DiscoveryCompletedEvent" in event_names
    assert "TopologyUpdatedEvent" not in event_names


async def test_run_job_exclude_rule_filters_target(
    db_session: AsyncSession, real_http_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = uuid.uuid4()
    profile = await seed_profile(db_session, organization_id=org_id)
    targets = DiscoveryTargetService(DiscoveryTargetRepository(db_session))
    await targets.create(
        organization_id=org_id,
        profile_id=profile.id,
        target_type=TargetType.HOST,
        address="192.0.2.10",
        protocol=ProtocolType.TCP,
    )
    await targets.create(
        organization_id=org_id,
        profile_id=profile.id,
        target_type=TargetType.HOST,
        address="192.0.2.99",
        protocol=ProtocolType.TCP,
    )
    rules = DiscoveryRuleService(DiscoveryRuleRepository(db_session))
    await rules.create(
        organization_id=org_id,
        profile_id=profile.id,
        rule_type=RuleType.EXCLUDE,
        field="address",
        operator="eq",
        value="192.0.2.99",
    )
    jobs = DiscoveryJobService(
        DiscoveryJobRepository(db_session), DiscoveryTargetRepository(db_session), db_session
    )
    job = await jobs.create_job(
        organization_id=org_id, profile_id=profile.id, mode=DiscoveryMode.MANUAL, triggered_by=None
    )

    fake_scanner = _FakeScanner(ScanOutcome(status=DiscoveryResultStatus.SUCCESS))
    monkeypatch.setattr(execution_module, "get_scanner", lambda protocol: fake_scanner)

    service = build_execution_service(db_session, real_http_client)
    result = await service.run_job(job.id, caller_token=None)

    assert result.total_targets == 1
    assert result.succeeded_targets == 1


async def test_run_job_include_rule_filters_target(
    db_session: AsyncSession, real_http_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = uuid.uuid4()
    profile = await seed_profile(db_session, organization_id=org_id)
    targets = DiscoveryTargetService(DiscoveryTargetRepository(db_session))
    await targets.create(
        organization_id=org_id,
        profile_id=profile.id,
        target_type=TargetType.HOST,
        address="192.0.2.10",
        protocol=ProtocolType.TCP,
    )
    await targets.create(
        organization_id=org_id,
        profile_id=profile.id,
        target_type=TargetType.HOST,
        address="192.0.2.99",
        protocol=ProtocolType.TCP,
    )
    rules = DiscoveryRuleService(DiscoveryRuleRepository(db_session))
    await rules.create(
        organization_id=org_id,
        profile_id=profile.id,
        rule_type=RuleType.INCLUDE,
        field="address",
        operator="eq",
        value="192.0.2.10",
    )
    jobs = DiscoveryJobService(
        DiscoveryJobRepository(db_session), DiscoveryTargetRepository(db_session), db_session
    )
    job = await jobs.create_job(
        organization_id=org_id, profile_id=profile.id, mode=DiscoveryMode.MANUAL, triggered_by=None
    )

    fake_scanner = _FakeScanner(ScanOutcome(status=DiscoveryResultStatus.SUCCESS))
    monkeypatch.setattr(execution_module, "get_scanner", lambda protocol: fake_scanner)

    service = build_execution_service(db_session, real_http_client)
    result = await service.run_job(job.id, caller_token=None)

    assert result.total_targets == 1


async def test_run_job_classification_rule_overrides_heuristic(
    db_session: AsyncSession, real_http_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = uuid.uuid4()
    profile = await seed_profile(db_session, organization_id=org_id)
    targets = DiscoveryTargetService(DiscoveryTargetRepository(db_session))
    await targets.create(
        organization_id=org_id,
        profile_id=profile.id,
        target_type=TargetType.HOST,
        address="industrial-plc-01.internal",
        protocol=ProtocolType.TCP,
    )
    rules = DiscoveryRuleService(DiscoveryRuleRepository(db_session))
    # A CLASSIFICATION rule's single `value` field does double duty --
    # it's both the match criterion (via matches_rule) and, if matched,
    # the AssetClassification name _classify() parses it as -- so it
    # can only usefully fire via "contains" against a real naming
    # convention where the classification is embedded in the candidate
    # (an "eq" rule would need the address to literally equal a
    # classification name).
    await rules.create(
        organization_id=org_id,
        profile_id=profile.id,
        rule_type=RuleType.CLASSIFICATION,
        field="address",
        operator="contains",
        value=AssetClassification.INDUSTRIAL.value,
    )
    jobs = DiscoveryJobService(
        DiscoveryJobRepository(db_session), DiscoveryTargetRepository(db_session), db_session
    )
    job = await jobs.create_job(
        organization_id=org_id, profile_id=profile.id, mode=DiscoveryMode.MANUAL, triggered_by=None
    )

    fake_scanner = _FakeScanner(ScanOutcome(status=DiscoveryResultStatus.SUCCESS))
    monkeypatch.setattr(execution_module, "get_scanner", lambda protocol: fake_scanner)

    service = build_execution_service(db_session, real_http_client)
    result = await service.run_job(job.id, caller_token=None)
    assert result.status == JobStatus.COMPLETED

    assets = await service._assets.list_for_job(job.id)
    assert len(assets) == 1
    assert assets[0].classification == AssetClassification.INDUSTRIAL


async def test_run_job_resolves_credential_and_syncs_asset(
    db_session: AsyncSession,
    real_http_client: AsyncClient,
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = uuid.uuid4()
    secret_id = uuid.uuid4()
    credential = await DiscoveryCredentialRepository(db_session).create(
        DiscoveryCredential(
            organization_id=org_id,
            name="ssh-cred",
            protocol=ProtocolType.SSH,
            credential_type=CredentialType.PASSWORD,
            secret_id=secret_id,
            username="admin",
        )
    )
    await db_session.flush()
    job = await _seed_job_with_target(
        db_session,
        organization_id=org_id,
        protocol=ProtocolType.SSH,
        credential_id=credential.id,
    )

    fake_scanner = _FakeScanner(ScanOutcome(status=DiscoveryResultStatus.SUCCESS))
    monkeypatch.setattr(execution_module, "get_scanner", lambda protocol: fake_scanner)

    httpx_mock.add_response(
        url=f"{SECRETS_SERVICE_BASE_URL}/secrets/{secret_id}",
        json={"data": {"value": "s3cr3t-pass"}},
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/assets",
        status_code=201,
        json={"data": {"id": str(uuid.uuid4())}},
    )

    service = build_execution_service(db_session, real_http_client)
    result = await service.run_job(job.id, caller_token="caller-token")

    assert result.status == JobStatus.COMPLETED
    assert fake_scanner.received_credential is not None
    assert fake_scanner.received_credential.password == "s3cr3t-pass"

    assets = await service._assets.list_for_job(job.id)
    assert assets[0].synced_to_inventory is True


async def test_run_job_credential_missing_caller_token_fails_target(
    db_session: AsyncSession, real_http_client: AsyncClient
) -> None:
    org_id = uuid.uuid4()
    secret_id = uuid.uuid4()
    credential = await DiscoveryCredentialRepository(db_session).create(
        DiscoveryCredential(
            organization_id=org_id,
            name="ssh-cred-2",
            protocol=ProtocolType.SSH,
            credential_type=CredentialType.PASSWORD,
            secret_id=secret_id,
            username="admin",
        )
    )
    await db_session.flush()
    job = await _seed_job_with_target(
        db_session,
        organization_id=org_id,
        protocol=ProtocolType.SSH,
        credential_id=credential.id,
    )

    service = build_execution_service(db_session, real_http_client)
    result = await service.run_job(job.id, caller_token=None)

    assert result.status == JobStatus.FAILED
    failures = await service._failures.list_for_job(job.id)
    assert failures[0].failure_reason == FailureReason.CREDENTIAL_MISSING


async def test_run_job_cloud_account_enumeration(
    db_session: AsyncSession, real_http_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = uuid.uuid4()
    job = await _seed_job_with_target(
        db_session,
        organization_id=org_id,
        target_type=TargetType.CLOUD_ACCOUNT,
        protocol=ProtocolType.HTTPS,
        address="123456789012",
        metadata={"cloud_vendor": "aws"},
    )
    provider = _FakeEnumerationProvider(
        resources=[
            DiscoveredResource(name="i-abc123", resource_type="instance", identity={}),
            DiscoveredResource(name="vpc-abc123", resource_type="vpc", identity={}),
        ]
    )
    monkeypatch.setattr(execution_module, "get_cloud_provider", lambda vendor: provider)

    service = build_execution_service(db_session, real_http_client)
    result = await service.run_job(job.id, caller_token=None)

    assert result.status == JobStatus.COMPLETED
    assert result.discovered_asset_count == 2


async def test_run_job_cloud_enumeration_error_fails_target(
    db_session: AsyncSession, real_http_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = uuid.uuid4()
    job = await _seed_job_with_target(
        db_session,
        organization_id=org_id,
        target_type=TargetType.CLOUD_ACCOUNT,
        protocol=ProtocolType.HTTPS,
        address="123456789012",
        metadata={"cloud_vendor": "aws"},
    )
    provider = _FakeEnumerationProvider(error=EnumerationError("bad credentials"))
    monkeypatch.setattr(execution_module, "get_cloud_provider", lambda vendor: provider)

    service = build_execution_service(db_session, real_http_client)
    result = await service.run_job(job.id, caller_token=None)

    assert result.status == JobStatus.FAILED
    failures = await service._failures.list_for_job(job.id)
    assert failures[0].failure_reason == FailureReason.PROTOCOL_ERROR


async def test_run_job_kubernetes_enumeration_infers_runs_on_relationship(
    db_session: AsyncSession, real_http_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = uuid.uuid4()
    job = await _seed_job_with_target(
        db_session,
        organization_id=org_id,
        target_type=TargetType.KUBERNETES_CLUSTER,
        protocol=ProtocolType.HTTPS,
        address="https://cluster.example.internal:6443",
    )
    provider = _FakeEnumerationProvider(
        resources=[
            DiscoveredResource(name="node-1", resource_type="node", identity={}),
            DiscoveredResource(name="pod-1", resource_type="pod", identity={"node_name": "node-1"}),
        ]
    )
    monkeypatch.setattr(execution_module, "KUBERNETES_PROVIDER", provider)

    published: list[object] = []

    async def _publish(event: object) -> None:
        published.append(event)

    service = build_execution_service(db_session, real_http_client, publish_event=_publish)
    result = await service.run_job(job.id, caller_token=None)

    assert result.status == JobStatus.COMPLETED
    assert result.discovered_relationship_count == 1
    relationships = await service._relationships.list_for_job(job.id)
    assert relationships[0].relationship_type == DiscoveryRelationshipType.RUNS_ON
    event_names = [type(event).__name__ for event in published]
    assert "TopologyUpdatedEvent" in event_names


async def test_run_job_all_targets_fail_marks_job_failed_and_publishes_failed_event(
    db_session: AsyncSession, real_http_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = uuid.uuid4()
    job = await _seed_job_with_target(db_session, organization_id=org_id)
    fake_scanner = _FakeScanner(
        ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message="no route")
    )
    monkeypatch.setattr(execution_module, "get_scanner", lambda protocol: fake_scanner)

    published: list[object] = []

    async def _publish(event: object) -> None:
        published.append(event)

    service = build_execution_service(db_session, real_http_client, publish_event=_publish)
    result = await service.run_job(job.id, caller_token=None)

    assert result.status == JobStatus.FAILED
    assert result.error_summary is not None
    event_names = [type(event).__name__ for event in published]
    assert "DiscoveryFailedEvent" in event_names
