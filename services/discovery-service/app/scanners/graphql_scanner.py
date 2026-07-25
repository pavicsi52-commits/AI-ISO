"""GraphQL scanner.

GraphQL is transported over plain HTTP POST with a JSON body -- there
is no separate wire protocol to implement, only a query shape every
GraphQL server accepts by convention (the schema introspection query).
This scanner sends the minimal real introspection query
(``{ __schema { queryType { name } } }``) and reports success only if
the response is genuinely well-formed GraphQL JSON (a ``data`` key
present, no top-level ``errors``), distinguishing a real GraphQL
endpoint from an arbitrary HTTP server that merely accepted the POST.
"""

from __future__ import annotations

import httpx

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_INTROSPECTION_QUERY = "{ __schema { queryType { name } } }"


def _parse_introspection_response(response: httpx.Response, *, latency_ms: float) -> ScanOutcome:
    """Validate that *response* is genuine GraphQL JSON, not just any HTTP 200."""
    if response.status_code in (401, 403):
        return ScanOutcome(status=DiscoveryResultStatus.AUTH_FAILED, latency_ms=latency_ms)
    try:
        body = response.json()
    except ValueError:
        return ScanOutcome(
            status=DiscoveryResultStatus.FAILURE,
            latency_ms=latency_ms,
            error_message="Response was not valid JSON.",
        )
    if not isinstance(body, dict) or "data" not in body:
        return ScanOutcome(
            status=DiscoveryResultStatus.FAILURE,
            latency_ms=latency_ms,
            error_message="Response did not contain a GraphQL 'data' field.",
        )
    query_type = ((body.get("data") or {}).get("__schema") or {}).get("queryType") or {}
    return ScanOutcome(
        status=DiscoveryResultStatus.SUCCESS,
        latency_ms=latency_ms,
        identity={"query_type_name": query_type.get("name")},
    )


class GraphQLScanner(ProtocolScanner):
    """POSTs a schema-introspection query and validates a real GraphQL response."""

    protocol = ProtocolType.GRAPHQL

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        netloc = address if port is None else f"{address}:{port}"
        url = f"http://{netloc}/graphql"
        headers = {"Content-Type": "application/json"}
        if credential is not None and credential.token:
            headers["Authorization"] = f"Bearer {credential.token}"

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(
                    url, json={"query": _INTROSPECTION_QUERY}, headers=headers
                )
        except httpx.TimeoutException:
            return ScanOutcome(status=DiscoveryResultStatus.TIMEOUT)
        except httpx.ConnectError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))
        except httpx.HTTPError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.FAILURE, error_message=str(exc))

        latency_ms = response.elapsed.total_seconds() * 1000
        return _parse_introspection_response(response, latency_ms=latency_ms)


__all__ = ["GraphQLScanner"]
