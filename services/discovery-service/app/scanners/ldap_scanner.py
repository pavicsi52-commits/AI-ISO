"""LDAP scanner, via ``ldap3``.

Also covers "Active Directory" (docs/037's own "OWNERSHIP"-adjacent
inventory concept, not a distinct wire protocol here -- AD speaks
standard LDAP/LDAPS on the wire, distinguished at the application layer
only by schema, which a generic discovery probe doesn't need to know).
Retrieves the server's real Root DSE (the standard, unauthenticated
LDAP way to identify a directory server -- vendor, supported LDAP
version, naming contexts) before attempting a bind, so a probe can
identify *something is an LDAP server* even without credentials.
"""

from __future__ import annotations

import asyncio
import time

import ldap3
from ldap3.core.exceptions import LDAPBindError, LDAPException, LDAPExceptionError

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_DEFAULT_PORT = 389


class LdapScanner(ProtocolScanner):
    """Reads a directory server's Root DSE, and binds if a credential is supplied."""

    protocol = ProtocolType.LDAP

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._connect, address, port or _DEFAULT_PORT, timeout_seconds, credential
        )

    def _connect(
        self, address: str, port: int, timeout_seconds: float, credential: ScanCredential | None
    ) -> ScanOutcome:
        server = ldap3.Server(
            address, port=port, connect_timeout=timeout_seconds, get_info=ldap3.ALL
        )
        start = time.perf_counter()
        user = credential.username if credential and credential.username else None
        password = credential.password if credential else None

        try:
            connection = ldap3.Connection(
                server,
                user=user,
                password=password,
                auto_bind=ldap3.AUTO_BIND_NO_TLS,
                receive_timeout=timeout_seconds,
            )
        except LDAPBindError as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            return ScanOutcome(
                status=DiscoveryResultStatus.AUTH_FAILED,
                latency_ms=latency_ms,
                error_message=str(exc),
            )
        except (LDAPException, LDAPExceptionError, OSError) as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))

        try:
            latency_ms = (time.perf_counter() - start) * 1000
            info = server.info
            identity = {
                "vendor_name": info.vendor_name if info else None,
                "vendor_version": info.vendor_version if info else None,
                "supported_ldap_versions": info.supported_ldap_versions if info else [],
                "naming_contexts": info.naming_contexts if info else [],
                "authenticated": connection.bound,
            }
            return ScanOutcome(
                status=DiscoveryResultStatus.SUCCESS, latency_ms=latency_ms, identity=identity
            )
        finally:
            # types-ldap3's own stub leaves Connection.unbind() untyped.
            connection.unbind()  # type: ignore[no-untyped-call]


__all__ = ["LdapScanner"]
