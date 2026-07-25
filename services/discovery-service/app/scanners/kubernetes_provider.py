"""Kubernetes discovery, via the official ``kubernetes`` Python client.

Per docs/037 "KUBERNETES DISCOVERY": Clusters, Namespaces, Nodes, Pods,
Deployments, StatefulSets, DaemonSets, Services, Ingress, ConfigMaps,
Secrets Metadata, Persistent Volumes, Persistent Volume Claims, Jobs,
CronJobs. "Secrets Metadata" means exactly that -- name/namespace/type
only, per docs/037's own platform-wide "never persist plaintext
credentials" rule; the value of a discovered ``Secret`` is never read.

**Live-verified against a real (mocked-at-the-HTTP-layer) Kubernetes
API server** (``tests/test_scanner_kubernetes.py``): the official
client's own wire format talking to a minimal local ASGI app that
implements just enough of the real Kubernetes REST API (list
namespaces/nodes/pods) to prove this provider parses genuine API
responses -- not a full ``kind``/``k3s`` cluster, which this
environment cannot run, but a real HTTP exchange against real client
code, the same "spin up a local server double" approach
``ldap_scanner.py``'s own LDAP MOCK_SYNC-equivalent testing uses.
"""

from __future__ import annotations

import asyncio

import urllib3.exceptions
from kubernetes import client as k8s_client

from app.models.enums import TargetType
from app.scanners.base import ScanCredential
from app.scanners.enumeration import DiscoveredResource, EnumerationError, EnumerationProvider


def _build_api_client(address: str, credential: ScanCredential | None) -> k8s_client.ApiClient:
    configuration = k8s_client.Configuration()
    configuration.host = address
    configuration.verify_ssl = False
    if credential is not None and credential.token:
        configuration.api_key["authorization"] = f"Bearer {credential.token}"
    return k8s_client.ApiClient(configuration)


class KubernetesProvider(EnumerationProvider):
    """Enumerates a cluster's namespaces, nodes, workloads, and networking objects."""

    target_type = TargetType.KUBERNETES_CLUSTER

    async def enumerate(
        self, address: str, *, credential: ScanCredential | None, timeout_seconds: float
    ) -> list[DiscoveredResource]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._enumerate, address, credential)

    def _enumerate(
        self, address: str, credential: ScanCredential | None
    ) -> list[DiscoveredResource]:
        api_client = _build_api_client(address, credential)
        core = k8s_client.CoreV1Api(api_client)
        apps = k8s_client.AppsV1Api(api_client)
        networking = k8s_client.NetworkingV1Api(api_client)
        batch = k8s_client.BatchV1Api(api_client)

        try:
            resources: list[DiscoveredResource] = []
            resources += self._list_namespaces(core)
            resources += self._list_nodes(core)
            resources += self._list_pods(core)
            resources += self._list_config_maps(core)
            resources += self._list_secrets_metadata(core)
            resources += self._list_persistent_volumes(core)
            resources += self._list_persistent_volume_claims(core)
            resources += self._list_services(core)
            resources += self._list_deployments(apps)
            resources += self._list_stateful_sets(apps)
            resources += self._list_daemon_sets(apps)
            resources += self._list_ingresses(networking)
            resources += self._list_jobs(batch)
            resources += self._list_cron_jobs(batch)
            return resources
        except k8s_client.ApiException as exc:
            if exc.status in (401, 403):
                raise EnumerationError(
                    f"Kubernetes API authentication/authorization failed: {exc}"
                ) from exc
            raise EnumerationError(f"Kubernetes API error: {exc}") from exc
        except (OSError, urllib3.exceptions.HTTPError) as exc:
            # A genuinely unreachable host (refused connection, DNS
            # failure, timeout) never actually raises a plain OSError
            # here -- the official client's own urllib3 transport wraps
            # it in urllib3.exceptions.MaxRetryError/NewConnectionError,
            # neither of which is an OSError subclass, so this except
            # clause never fired for the one case it exists for until
            # this package's own live test suite caught it: an
            # unreachable cluster crashed the whole enumeration with an
            # unhandled urllib3 exception instead of a clean
            # EnumerationError.
            raise EnumerationError(f"Kubernetes API unreachable: {exc}") from exc
        finally:
            api_client.close()

    @staticmethod
    def _list_namespaces(core: k8s_client.CoreV1Api) -> list[DiscoveredResource]:
        return [
            DiscoveredResource(name=item.metadata.name, resource_type="namespace")
            for item in core.list_namespace().items
        ]

    @staticmethod
    def _list_nodes(core: k8s_client.CoreV1Api) -> list[DiscoveredResource]:
        return [
            DiscoveredResource(
                name=item.metadata.name,
                resource_type="node",
                identity={
                    "kubelet_version": (
                        item.status.node_info.kubelet_version
                        if item.status and item.status.node_info
                        else None
                    ),
                    "os_image": (
                        item.status.node_info.os_image
                        if item.status and item.status.node_info
                        else None
                    ),
                },
            )
            for item in core.list_node().items
        ]

    @staticmethod
    def _list_pods(core: k8s_client.CoreV1Api) -> list[DiscoveredResource]:
        return [
            DiscoveredResource(
                name=item.metadata.name,
                resource_type="pod",
                identity={
                    "namespace": item.metadata.namespace,
                    "phase": item.status.phase,
                    "node_name": item.spec.node_name if item.spec else None,
                },
            )
            for item in core.list_pod_for_all_namespaces().items
        ]

    @staticmethod
    def _list_config_maps(core: k8s_client.CoreV1Api) -> list[DiscoveredResource]:
        return [
            DiscoveredResource(
                name=item.metadata.name,
                resource_type="config_map",
                identity={"namespace": item.metadata.namespace},
            )
            for item in core.list_config_map_for_all_namespaces().items
        ]

    @staticmethod
    def _list_secrets_metadata(core: k8s_client.CoreV1Api) -> list[DiscoveredResource]:
        return [
            DiscoveredResource(
                name=item.metadata.name,
                resource_type="secret",
                identity={"namespace": item.metadata.namespace, "type": item.type},
            )
            for item in core.list_secret_for_all_namespaces().items
        ]

    @staticmethod
    def _list_persistent_volumes(core: k8s_client.CoreV1Api) -> list[DiscoveredResource]:
        return [
            DiscoveredResource(name=item.metadata.name, resource_type="persistent_volume")
            for item in core.list_persistent_volume().items
        ]

    @staticmethod
    def _list_persistent_volume_claims(core: k8s_client.CoreV1Api) -> list[DiscoveredResource]:
        return [
            DiscoveredResource(
                name=item.metadata.name,
                resource_type="persistent_volume_claim",
                identity={"namespace": item.metadata.namespace},
            )
            for item in core.list_persistent_volume_claim_for_all_namespaces().items
        ]

    @staticmethod
    def _list_services(core: k8s_client.CoreV1Api) -> list[DiscoveredResource]:
        return [
            DiscoveredResource(
                name=item.metadata.name,
                resource_type="service",
                identity={"namespace": item.metadata.namespace, "type": item.spec.type},
            )
            for item in core.list_service_for_all_namespaces().items
        ]

    @staticmethod
    def _list_deployments(apps: k8s_client.AppsV1Api) -> list[DiscoveredResource]:
        return [
            DiscoveredResource(
                name=item.metadata.name,
                resource_type="deployment",
                identity={"namespace": item.metadata.namespace, "replicas": item.spec.replicas},
            )
            for item in apps.list_deployment_for_all_namespaces().items
        ]

    @staticmethod
    def _list_stateful_sets(apps: k8s_client.AppsV1Api) -> list[DiscoveredResource]:
        return [
            DiscoveredResource(
                name=item.metadata.name,
                resource_type="stateful_set",
                identity={"namespace": item.metadata.namespace},
            )
            for item in apps.list_stateful_set_for_all_namespaces().items
        ]

    @staticmethod
    def _list_daemon_sets(apps: k8s_client.AppsV1Api) -> list[DiscoveredResource]:
        return [
            DiscoveredResource(
                name=item.metadata.name,
                resource_type="daemon_set",
                identity={"namespace": item.metadata.namespace},
            )
            for item in apps.list_daemon_set_for_all_namespaces().items
        ]

    @staticmethod
    def _list_ingresses(networking: k8s_client.NetworkingV1Api) -> list[DiscoveredResource]:
        return [
            DiscoveredResource(
                name=item.metadata.name,
                resource_type="ingress",
                identity={"namespace": item.metadata.namespace},
            )
            for item in networking.list_ingress_for_all_namespaces().items
        ]

    @staticmethod
    def _list_jobs(batch: k8s_client.BatchV1Api) -> list[DiscoveredResource]:
        return [
            DiscoveredResource(
                name=item.metadata.name,
                resource_type="job",
                identity={"namespace": item.metadata.namespace},
            )
            for item in batch.list_job_for_all_namespaces().items
        ]

    @staticmethod
    def _list_cron_jobs(batch: k8s_client.BatchV1Api) -> list[DiscoveredResource]:
        return [
            DiscoveredResource(
                name=item.metadata.name,
                resource_type="cron_job",
                identity={"namespace": item.metadata.namespace, "schedule": item.spec.schedule},
            )
            for item in batch.list_cron_job_for_all_namespaces().items
        ]


__all__ = ["KubernetesProvider"]
