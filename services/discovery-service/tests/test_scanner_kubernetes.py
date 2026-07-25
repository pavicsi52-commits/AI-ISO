"""Tests for :class:`app.scanners.kubernetes_provider.KubernetesProvider`
against a real, local HTTP server this test module starts itself -- a
minimal implementation of just the 14 real Kubernetes REST API list
endpoints this provider calls (see its own module docstring). The
official ``kubernetes`` client's own ``urllib3``-based wire format
talks to this server over a genuine HTTP connection, so this proves
real request-building/response-parsing, not a simulation -- it just
isn't a full ``kind``/``k3s`` cluster, which this environment can't run.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.scanners.base import ScanCredential
from app.scanners.enumeration import EnumerationError
from app.scanners.kubernetes_provider import KubernetesProvider

_TIMEOUT_SECONDS = 5.0


def _list_response(kind: str, items: list[dict[str, object]]) -> dict[str, object]:
    return {"kind": kind, "apiVersion": "v1", "metadata": {}, "items": items}


_WORKLOAD_SPEC: dict[str, object] = {
    "selector": {"matchLabels": {"app": "demo"}},
    "template": {
        "metadata": {"labels": {"app": "demo"}},
        "spec": {"containers": [{"name": "app", "image": "nginx:1.27"}]},
    },
}
"""The ``selector``/``template`` pair every real Kubernetes workload
spec (``Deployment``/``StatefulSet``/``DaemonSet``) requires -- the
official client's own generated models reject a response missing
either with a real ``ValueError`` at deserialization time, caught live
while building this fixture data against real client code.
"""


_RESPONSES: dict[str, dict[str, object]] = {
    "/api/v1/namespaces": _list_response("NamespaceList", [{"metadata": {"name": "default"}}]),
    "/api/v1/nodes": _list_response(
        "NodeList",
        [
            {
                "metadata": {"name": "node-1"},
                "status": {
                    "nodeInfo": {
                        "architecture": "amd64",
                        "bootID": "boot-1",
                        "containerRuntimeVersion": "containerd://1.7.0",
                        "kernelVersion": "5.15.0",
                        "kubeProxyVersion": "v1.29.0",
                        "kubeletVersion": "v1.29.0",
                        "machineID": "machine-1",
                        "operatingSystem": "linux",
                        "osImage": "Ubuntu 22.04",
                        "systemUUID": "uuid-1",
                    }
                },
            }
        ],
    ),
    "/api/v1/pods": _list_response(
        "PodList",
        [
            {
                "metadata": {"name": "pod-1", "namespace": "default"},
                "spec": {
                    "nodeName": "node-1",
                    "containers": [{"name": "app", "image": "nginx:1.27"}],
                },
                "status": {"phase": "Running"},
            }
        ],
    ),
    "/api/v1/configmaps": _list_response(
        "ConfigMapList", [{"metadata": {"name": "cm-1", "namespace": "default"}}]
    ),
    "/api/v1/secrets": _list_response(
        "SecretList",
        [{"metadata": {"name": "secret-1", "namespace": "default"}, "type": "Opaque"}],
    ),
    "/api/v1/persistentvolumes": _list_response(
        "PersistentVolumeList", [{"metadata": {"name": "pv-1"}}]
    ),
    "/api/v1/persistentvolumeclaims": _list_response(
        "PersistentVolumeClaimList",
        [{"metadata": {"name": "pvc-1", "namespace": "default"}}],
    ),
    "/api/v1/services": _list_response(
        "ServiceList",
        [
            {
                "metadata": {"name": "svc-1", "namespace": "default"},
                "spec": {"type": "ClusterIP"},
            }
        ],
    ),
    "/apis/apps/v1/deployments": _list_response(
        "DeploymentList",
        [
            {
                "metadata": {"name": "deploy-1", "namespace": "default"},
                "spec": {"replicas": 3, **_WORKLOAD_SPEC},
            }
        ],
    ),
    "/apis/apps/v1/statefulsets": _list_response(
        "StatefulSetList",
        [
            {
                "metadata": {"name": "sts-1", "namespace": "default"},
                "spec": {"serviceName": "sts-1", **_WORKLOAD_SPEC},
            }
        ],
    ),
    "/apis/apps/v1/daemonsets": _list_response(
        "DaemonSetList",
        [{"metadata": {"name": "ds-1", "namespace": "default"}, "spec": _WORKLOAD_SPEC}],
    ),
    "/apis/networking.k8s.io/v1/ingresses": _list_response(
        "IngressList", [{"metadata": {"name": "ing-1", "namespace": "default"}}]
    ),
    "/apis/batch/v1/jobs": _list_response(
        "JobList", [{"metadata": {"name": "job-1", "namespace": "default"}}]
    ),
    "/apis/batch/v1/cronjobs": _list_response(
        "CronJobList",
        [
            {
                "metadata": {"name": "cronjob-1", "namespace": "default"},
                "spec": {
                    "schedule": "0 * * * *",
                    "jobTemplate": {"spec": {"template": _WORKLOAD_SPEC["template"]}},
                },
            }
        ],
    ),
}


class _FakeKubernetesApiHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        body = _RESPONSES.get(path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        pass  # keep pytest's own output clean


class _FailingApiHandler(BaseHTTPRequestHandler):
    def __init__(self, *args: object, status: int, **kwargs: object) -> None:
        self._status = status
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def do_GET(self) -> None:
        self.send_response(self._status)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def fake_k8s_api() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _FakeKubernetesApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=_TIMEOUT_SECONDS)


async def test_enumerate_parses_every_real_resource_type(fake_k8s_api: str) -> None:
    resources = await KubernetesProvider().enumerate(
        fake_k8s_api, credential=None, timeout_seconds=_TIMEOUT_SECONDS
    )
    by_type = {resource.resource_type: resource for resource in resources}
    assert set(by_type) == {
        "namespace",
        "node",
        "pod",
        "config_map",
        "secret",
        "persistent_volume",
        "persistent_volume_claim",
        "service",
        "deployment",
        "stateful_set",
        "daemon_set",
        "ingress",
        "job",
        "cron_job",
    }
    assert by_type["node"].identity["kubelet_version"] == "v1.29.0"
    assert by_type["pod"].identity["node_name"] == "node-1"
    assert by_type["pod"].identity["namespace"] == "default"
    assert by_type["secret"].identity["type"] == "Opaque"
    assert by_type["deployment"].identity["replicas"] == 3
    assert by_type["cron_job"].identity["schedule"] == "0 * * * *"


async def test_enumerate_uses_bearer_token_credential(fake_k8s_api: str) -> None:
    credential = ScanCredential(token="a-real-looking-token")
    resources = await KubernetesProvider().enumerate(
        fake_k8s_api, credential=credential, timeout_seconds=_TIMEOUT_SECONDS
    )
    assert len(resources) == 14


async def test_enumerate_401_raises_enumeration_error() -> None:
    def _handler_factory(*args: object, **kwargs: object) -> _FailingApiHandler:
        return _FailingApiHandler(*args, status=401, **kwargs)

    server = HTTPServer(("127.0.0.1", 0), _handler_factory)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(EnumerationError, match="authentication/authorization"):
            await KubernetesProvider().enumerate(
                f"http://127.0.0.1:{server.server_port}",
                credential=None,
                timeout_seconds=_TIMEOUT_SECONDS,
            )
    finally:
        server.shutdown()
        thread.join(timeout=_TIMEOUT_SECONDS)


async def test_enumerate_unreachable_host_raises_enumeration_error() -> None:
    with pytest.raises(EnumerationError, match="unreachable"):
        await KubernetesProvider().enumerate(
            "http://127.0.0.1:1", credential=None, timeout_seconds=1
        )
