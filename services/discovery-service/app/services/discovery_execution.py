"""The discovery job runner -- the orchestrator every other service in
this package feeds into.

Per docs/037's own functional sections this ties together: probes every
target (protocol scanners for host-shaped targets, enumeration
providers for cloud accounts/Kubernetes clusters -- see
``app/scanners/registry.py``), classifies and fingerprints what it
finds, synchronizes assets/relationships into the Inventory Service,
and records results/failures/history/audit/statistics along the way.

**A known, honestly-documented limitation for scheduler-triggered
runs**: every downstream call this service makes (credential
resolution against ``services/secrets-management-service``, asset/
relationship sync against ``services/inventory-service``) requires a
caller identity Bearer token, since both of those services require
authentication on every endpoint. Interactively-triggered jobs (every
``POST /discovery/*`` REST endpoint) always have one -- the triggering
request's own token flows straight through the queue message to the
worker that calls :meth:`run_job`. A job fired autonomously by
``shared_core.scheduler`` (no live HTTP request behind it) has no such
token, since no prior AI-IOS prompt establishes a service-account/
machine-credential mechanism -- the same class of platform gap
``packages/shared-core/connectors``' own deferred-providers scope note
already flagged, not a shortcut taken here to avoid work. With
``caller_token=None``, this method still runs every credential-less
protocol probe (TCP/UDP/ICMP/DNS/NTP/HTTP/HTTPS/GraphQL/AMQP/anonymous-
MQTT/anonymous-LDAP/public-community-SNMP all function without
resolved credentials) and still records every local
``discovery_results``/``discovery_assets`` row, but skips credential
resolution (any protocol that strictly requires one fails with
``CREDENTIAL_MISSING``) and leaves every discovered asset
``sync_status=PENDING`` rather than attempting an Inventory Service
call with no identity to present.

**A documented, bounded "DISCOVERY RULES" scope limit**: of the nine
:class:`~app.models.enums.RuleType` values, only ``INCLUDE``/
``EXCLUDE`` (applied to every target's own ``address`` before probing,
via :func:`~app.services.rule.matches_rule` -- see that function's own
docstring for the eq/ne/contains-only scope limit it already
establishes) and ``CLASSIFICATION`` (applied after fingerprinting, able
to override :func:`~app.classification.classifier.classify_by_protocol`
/``classify_by_resource_type``'s own heuristic result -- every
classification decision, heuristic or rule-overridden, is recorded via
:class:`~app.services.classification.DiscoveryClassificationService`)
are evaluated by this engine. ``FILTER``/``ASSET_MATCHING`` have no
application semantics docs/037 specifies beyond a one-line "Support"
mention, and ``RELATIONSHIP``/``TAG_ASSIGNMENT``/``OWNER_ASSIGNMENT``/
``PROJECT_ASSIGNMENT`` would need schema fields
:class:`~app.models.discovery_asset.DiscoveryAsset` doesn't have (no
tag/owner/project columns exist on it) -- the same "bounded, not
exhaustive" judgment this engine's own Kubernetes-only relationship
inference already applies to a different dimension. A
:class:`~app.models.discovery_rule.DiscoveryRule` of one of those four
types can still be created and stored via
:class:`~app.services.rule.DiscoveryRuleService`; it's simply never
read by this engine.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.enums.job_status import JobStatus
from shared_core.events.base import DomainEvent

from app.classification.classifier import classify_by_protocol, classify_by_resource_type
from app.classification.fingerprint import merge_fingerprint
from app.discovery.credentials import CredentialResolver
from app.events.discovery_events import (
    DiscoveryCompletedEvent,
    DiscoveryFailedEvent,
    DiscoveryStartedEvent,
    TopologyUpdatedEvent,
)
from app.models.discovery_job import DiscoveryJob
from app.models.discovery_rule import DiscoveryRule
from app.models.discovery_target import DiscoveryTarget
from app.models.enums import (
    AssetClassification,
    ClassifiedBy,
    DiscoveryRelationshipType,
    DiscoveryResultStatus,
    FailureReason,
    ProtocolType,
    RuleType,
    TargetType,
)
from app.scanners.base import ScanCredential
from app.scanners.enumeration import DiscoveredResource, EnumerationError, EnumerationProvider
from app.scanners.registry import KUBERNETES_PROVIDER, get_cloud_provider, get_scanner
from app.services.asset import DiscoveryAssetService
from app.services.audit import DiscoveryAuditService
from app.services.classification import DiscoveryClassificationService
from app.services.credential import DiscoveryCredentialService
from app.services.failure import DiscoveryFailureService
from app.services.history import DiscoveryHistoryService
from app.services.job import DiscoveryJobService
from app.services.relationship import DiscoveryRelationshipService
from app.services.result import DiscoveryResultService
from app.services.rule import DiscoveryRuleService, matches_rule
from app.services.target import DiscoveryTargetService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_UNKNOWN_ASSET_TYPE = "unknown"
_SOURCE_SERVICE = "discovery-service"


class DiscoveryExecutionService:
    """Runs one discovery job to completion: probes every target,
    classifies/fingerprints/records what it finds, and synchronizes
    into the Inventory Service.
    """

    def __init__(
        self,
        jobs: DiscoveryJobService,
        targets: DiscoveryTargetService,
        credentials: DiscoveryCredentialService,
        results: DiscoveryResultService,
        assets: DiscoveryAssetService,
        relationships: DiscoveryRelationshipService,
        failures: DiscoveryFailureService,
        history: DiscoveryHistoryService,
        audit: DiscoveryAuditService,
        credential_resolver: CredentialResolver,
        rules: DiscoveryRuleService,
        classifications: DiscoveryClassificationService,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._jobs = jobs
        self._targets = targets
        self._credentials = credentials
        self._results = results
        self._assets = assets
        self._relationships = relationships
        self._failures = failures
        self._history = history
        self._audit = audit
        self._credential_resolver = credential_resolver
        self._rules = rules
        self._classifications = classifications
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def run_job(self, job_id: UUID, *, caller_token: str | None) -> DiscoveryJob:
        """Execute *job_id*'s targets to completion.

        Raises:
            ConflictError: If *job_id* isn't in a processable state
                (surfaced by the caller's own repository lookup, not
                raised directly here).
        """
        job = await self._jobs.get_by_id(job_id)
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        await self._history.record(
            job.id, organization_id=job.organization_id, event_type="started"
        )
        await self._publish(
            DiscoveryStartedEvent(
                source_service=_SOURCE_SERVICE,
                organization_id=job.organization_id,
                payload={"job_id": str(job.id)},
            )
        )

        targets = await self._targets.list_for_profile(job.profile_id) if job.profile_id else []
        rules = await self._rules.list_for_profile(job.profile_id) if job.profile_id else []
        targets = _filter_included_targets(targets, rules)
        job.total_targets = len(targets)

        asset_ids_by_target: dict[UUID, list[UUID]] = {}
        for target in targets:
            try:
                asset_ids = await self._run_target(
                    job, target, rules=rules, caller_token=caller_token
                )
                asset_ids_by_target[target.id] = asset_ids
                job.succeeded_targets += 1
            except _TargetFailedError as exc:
                job.failed_targets += 1
                await self._failures.record(
                    job.id,
                    organization_id=job.organization_id,
                    target_id=target.id,
                    protocol=target.protocol,
                    failure_reason=exc.reason,
                    error_detail=exc.detail,
                )

        job.discovered_asset_count = sum(len(ids) for ids in asset_ids_by_target.values())
        job.discovered_relationship_count = len(await self._relationships.list_for_job(job.id))
        job.completed_at = datetime.now(UTC)

        all_targets_failed = job.total_targets > 0 and job.succeeded_targets == 0
        job.status = JobStatus.FAILED if all_targets_failed else JobStatus.COMPLETED
        if all_targets_failed:
            job.error_summary = f"All {job.failed_targets} target(s) failed."

        await self._history.record(
            job.id,
            organization_id=job.organization_id,
            event_type=str(job.status),
            detail={
                "succeeded_targets": job.succeeded_targets,
                "failed_targets": job.failed_targets,
            },
        )
        await self._audit.record(
            job.id,
            organization_id=job.organization_id,
            actor_id=job.triggered_by,
            action="execute",
            after={"status": str(job.status), "discovered_asset_count": job.discovered_asset_count},
        )
        if job.status == JobStatus.FAILED:
            await self._publish(
                DiscoveryFailedEvent(
                    source_service=_SOURCE_SERVICE,
                    organization_id=job.organization_id,
                    payload={"job_id": str(job.id), "error_summary": job.error_summary},
                )
            )
        else:
            await self._publish(
                DiscoveryCompletedEvent(
                    source_service=_SOURCE_SERVICE,
                    organization_id=job.organization_id,
                    payload={
                        "job_id": str(job.id),
                        "discovered_asset_count": job.discovered_asset_count,
                    },
                )
            )
        if job.discovered_relationship_count > 0:
            await self._publish(
                TopologyUpdatedEvent(
                    source_service=_SOURCE_SERVICE,
                    organization_id=job.organization_id,
                    payload={
                        "job_id": str(job.id),
                        "discovered_relationship_count": job.discovered_relationship_count,
                    },
                )
            )
        return job

    async def _run_target(
        self,
        job: DiscoveryJob,
        target: DiscoveryTarget,
        *,
        rules: list[DiscoveryRule],
        caller_token: str | None,
    ) -> list[UUID]:
        credential = await self._resolve_credential(target, caller_token=caller_token)

        if target.target_type == TargetType.KUBERNETES_CLUSTER:
            return await self._run_enumeration(
                job,
                target,
                credential=credential,
                vendor=None,
                rules=rules,
                caller_token=caller_token,
            )
        if target.target_type == TargetType.CLOUD_ACCOUNT:
            vendor = str(target.metadata_.get("cloud_vendor", ""))
            return await self._run_enumeration(
                job,
                target,
                credential=credential,
                vendor=vendor,
                rules=rules,
                caller_token=caller_token,
            )
        return await self._run_protocol_probe(
            job, target, credential=credential, rules=rules, caller_token=caller_token
        )

    async def _resolve_credential(
        self, target: DiscoveryTarget, *, caller_token: str | None
    ) -> ScanCredential | None:
        if target.credential_id is None:
            return None
        if caller_token is None:
            raise _TargetFailedError(
                FailureReason.CREDENTIAL_MISSING,
                "No caller identity available to resolve this target's credential.",
            )
        credential_ref = await self._credentials.get_by_id(target.credential_id)
        return await self._credential_resolver.resolve(credential_ref, caller_token=caller_token)

    async def _run_protocol_probe(
        self,
        job: DiscoveryJob,
        target: DiscoveryTarget,
        *,
        credential: ScanCredential | None,
        rules: list[DiscoveryRule],
        caller_token: str | None,
    ) -> list[UUID]:
        scanner = get_scanner(target.protocol)
        outcome = await scanner.probe(
            target.address, port=target.port, timeout_seconds=30, credential=credential
        )
        result = await self._results.record(
            job.id,
            target.id,
            organization_id=job.organization_id,
            protocol=target.protocol,
            status=outcome.status,
            latency_ms=outcome.latency_ms,
            raw_data=outcome.identity,
            error_message=outcome.error_message,
        )
        if outcome.status != DiscoveryResultStatus.SUCCESS:
            raise _TargetFailedError(_failure_reason_for(outcome.status), outcome.error_message)

        classification, classified_by, rule_id = _classify(
            rules, target.address, classify_by_protocol(target.protocol)
        )
        fingerprint = merge_fingerprint([(target.protocol, outcome.identity)])
        asset = await self._assets.record(
            job.id,
            result.id,
            organization_id=job.organization_id,
            name=target.address,
            asset_type=_UNKNOWN_ASSET_TYPE,
            classification=classification,
            fingerprint=fingerprint,
        )
        await self._classifications.record(
            asset.id,
            organization_id=job.organization_id,
            classification=classification,
            classified_by=classified_by,
            rule_id=rule_id,
        )
        if caller_token is not None:
            await self._assets.sync_to_inventory(
                asset,
                organization_id=job.organization_id,
                caller_token=caller_token,
                identifiers=_identifiers_for(target, outcome.identity),
            )
        return [asset.id]

    async def _run_enumeration(
        self,
        job: DiscoveryJob,
        target: DiscoveryTarget,
        *,
        credential: ScanCredential | None,
        vendor: str | None,
        rules: list[DiscoveryRule],
        caller_token: str | None,
    ) -> list[UUID]:
        provider: EnumerationProvider = (
            get_cloud_provider(vendor) if vendor else KUBERNETES_PROVIDER
        )
        try:
            discovered = await provider.enumerate(
                target.address, credential=credential, timeout_seconds=60
            )
        except EnumerationError as exc:
            await self._results.record(
                job.id,
                target.id,
                organization_id=job.organization_id,
                protocol=target.protocol,
                status=DiscoveryResultStatus.FAILURE,
                latency_ms=None,
                raw_data={},
                error_message=str(exc),
            )
            raise _TargetFailedError(FailureReason.PROTOCOL_ERROR, str(exc)) from exc

        result = await self._results.record(
            job.id,
            target.id,
            organization_id=job.organization_id,
            protocol=target.protocol,
            status=DiscoveryResultStatus.SUCCESS,
            latency_ms=None,
            raw_data={"resource_count": len(discovered)},
            error_message=None,
        )

        asset_ids: list[UUID] = []
        for resource in discovered:
            classification, classified_by, rule_id = _classify(
                rules, resource.name, classify_by_resource_type(resource.resource_type)
            )
            asset = await self._assets.record(
                job.id,
                result.id,
                organization_id=job.organization_id,
                name=resource.name,
                asset_type=resource.resource_type,
                classification=classification,
                fingerprint=resource.identity,
            )
            await self._classifications.record(
                asset.id,
                organization_id=job.organization_id,
                classification=classification,
                classified_by=classified_by,
                rule_id=rule_id,
            )
            if caller_token is not None:
                await self._assets.sync_to_inventory(
                    asset,
                    organization_id=job.organization_id,
                    caller_token=caller_token,
                    identifiers={},
                )
            asset_ids.append(asset.id)

        await self._infer_kubernetes_relationships(
            job, discovered, asset_ids, caller_token=caller_token
        )
        return asset_ids

    async def _infer_kubernetes_relationships(
        self,
        job: DiscoveryJob,
        discovered: list[DiscoveredResource],
        asset_ids: list[UUID],
        *,
        caller_token: str | None,
    ) -> None:
        """Infer ``RUNS_ON`` edges between Kubernetes pods and their
        node -- the one concrete relationship-inference pass this
        service implements; deeper cross-resource inference (e.g. a
        cloud instance's subnet/VPC chain) is a documented scope limit,
        the same "bounded, not exhaustive" judgment
        ``services/inventory-service``'s own ``AssetGroupService`` rule
        evaluator already applied to filter operators.
        """
        node_asset_id_by_name = {
            resource.name: asset_id
            for resource, asset_id in zip(discovered, asset_ids, strict=True)
            if resource.resource_type == "node"
        }
        pod_edges = [
            (asset_id, node_asset_id_by_name[resource.identity["node_name"]])
            for resource, asset_id in zip(discovered, asset_ids, strict=True)
            if resource.resource_type == "pod"
            and resource.identity.get("node_name") in node_asset_id_by_name
        ]
        if not pod_edges:
            return

        assets_by_id = {asset.id: asset for asset in await self._assets.list_for_job(job.id)}
        for pod_asset_id, node_asset_id in pod_edges:
            relationship = await self._relationships.record(
                job.id,
                organization_id=job.organization_id,
                source_discovery_asset_id=pod_asset_id,
                target_discovery_asset_id=node_asset_id,
                relationship_type=DiscoveryRelationshipType.RUNS_ON,
            )
            if caller_token is None:
                continue
            source_asset = assets_by_id.get(pod_asset_id)
            target_asset = assets_by_id.get(node_asset_id)
            if source_asset is not None and target_asset is not None:
                await self._relationships.sync_to_inventory(
                    relationship,
                    organization_id=job.organization_id,
                    source_asset=source_asset,
                    target_asset=target_asset,
                    caller_token=caller_token,
                )


class _TargetFailedError(Exception):
    """Raised internally to short-circuit one target's processing with
    a specific :class:`~app.models.enums.FailureReason`.
    """

    def __init__(self, reason: FailureReason, detail: str | None) -> None:
        super().__init__(detail or reason.value)
        self.reason = reason
        self.detail = detail


def _failure_reason_for(status: DiscoveryResultStatus) -> FailureReason:
    return {
        DiscoveryResultStatus.TIMEOUT: FailureReason.TIMEOUT,
        DiscoveryResultStatus.UNREACHABLE: FailureReason.UNREACHABLE,
        DiscoveryResultStatus.AUTH_FAILED: FailureReason.AUTH_FAILED,
        DiscoveryResultStatus.FAILURE: FailureReason.PROTOCOL_ERROR,
    }.get(status, FailureReason.UNKNOWN)


def _identifiers_for(target: DiscoveryTarget, identity: dict[str, Any]) -> dict[str, str | None]:
    identifiers: dict[str, str | None] = {"ip_address": None, "hostname": None}
    if target.protocol in (ProtocolType.TCP, ProtocolType.ICMP):
        identifiers["ip_address"] = target.address
    else:
        identifiers["hostname"] = target.address
    return identifiers


def _filter_included_targets(
    targets: list[DiscoveryTarget], rules: list[DiscoveryRule]
) -> list[DiscoveryTarget]:
    """Apply this profile's own ``INCLUDE``/``EXCLUDE`` rules ("Include
    Rules", "Exclude Rules") before probing: a target matching any
    ``EXCLUDE`` rule is dropped; if any ``INCLUDE`` rules exist, only
    targets matching at least one of them survive. See this module's
    own docstring for the rule-type scope limit this is part of.
    """
    include_rules = [rule for rule in rules if rule.rule_type == RuleType.INCLUDE]
    exclude_rules = [rule for rule in rules if rule.rule_type == RuleType.EXCLUDE]
    if not include_rules and not exclude_rules:
        return targets
    return [
        target
        for target in targets
        if not any(matches_rule(rule, target.address) for rule in exclude_rules)
        and (not include_rules or any(matches_rule(rule, target.address) for rule in include_rules))
    ]


def _classify(
    rules: list[DiscoveryRule], candidate: str, heuristic: AssetClassification
) -> tuple[AssetClassification, ClassifiedBy, UUID | None]:
    """Apply this profile's own ``CLASSIFICATION`` rules, falling back
    to *heuristic* (:func:`~app.classification.classifier
    .classify_by_protocol`/``classify_by_resource_type``'s own result)
    when none match. The first matching rule wins.
    """
    for rule in rules:
        if rule.rule_type != RuleType.CLASSIFICATION or not matches_rule(rule, candidate):
            continue
        try:
            return AssetClassification(str(rule.value)), ClassifiedBy.RULE, rule.id
        except ValueError:
            continue
    return heuristic, ClassifiedBy.HEURISTIC, None


__all__ = ["DiscoveryExecutionService"]
