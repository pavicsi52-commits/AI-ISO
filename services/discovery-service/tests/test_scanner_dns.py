"""Real-network tests for :mod:`app.scanners.dns_scanner`.

This machine has real internet access (see this package's own
``tests/conftest.py`` module docstring's "real infrastructure wherever
genuinely feasible" discipline), so every test here performs a genuine
DNS query against the live public DNS system -- no mocking, except for
the two branches (a real network timeout, an arbitrary
``dns.exception.DNSException``) no live query can deterministically
reproduce.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import dns.asyncresolver
import dns.exception
import pytest

from app.models.enums import DiscoveryResultStatus
from app.scanners.dns_scanner import DnsScanner

_TIMEOUT_SECONDS = 5.0


class TestDnsScanner:
    async def test_success_resolving_a_real_hostname(self) -> None:
        outcome = await DnsScanner().probe(
            "cloudflare.com", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
        )
        assert outcome.status == DiscoveryResultStatus.SUCCESS
        assert outcome.latency_ms is not None
        addresses = outcome.identity["addresses"]
        assert isinstance(addresses, list)
        assert len(addresses) > 0
        for address in addresses:
            parts = address.split(".")
            assert len(parts) == 4
            assert all(part.isdigit() for part in parts)
        assert isinstance(outcome.identity["ttl"], int)

    async def test_nxdomain_is_failure(self) -> None:
        """A genuinely nonexistent hostname under a real TLD -- the
        resolver performs a real query and gets a real NXDOMAIN back.
        """
        outcome = await DnsScanner().probe(
            "this-hostname-genuinely-does-not-exist-aiios-discovery-test.invalid",
            port=None,
            timeout_seconds=_TIMEOUT_SECONDS,
            credential=None,
        )
        assert outcome.status == DiscoveryResultStatus.FAILURE
        assert outcome.error_message is not None
        assert "does not exist" in outcome.error_message

    async def test_success_with_multiple_a_records(self) -> None:
        """``one.one.one.one`` (Cloudflare's own resolver hostname)
        deterministically resolves to both of its two well-known
        addresses -- a real query exercising the multi-record branch of
        ``identity["addresses"]``.
        """
        outcome = await DnsScanner().probe(
            "one.one.one.one", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
        )
        assert outcome.status == DiscoveryResultStatus.SUCCESS
        assert set(outcome.identity["addresses"]) == {"1.1.1.1", "1.0.0.1"}

    async def test_timeout_maps_to_timeout_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            dns.asyncresolver.Resolver,
            "resolve",
            AsyncMock(side_effect=dns.exception.Timeout()),  # type: ignore[no-untyped-call]
        )
        outcome = await DnsScanner().probe(
            "example.com", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
        )
        assert outcome.status == DiscoveryResultStatus.TIMEOUT

    async def test_generic_dns_exception_maps_to_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            dns.asyncresolver.Resolver,
            "resolve",
            # dnspython's own stubs leave DNSException.__init__ untyped.
            AsyncMock(side_effect=dns.exception.DNSException("no nameservers")),  # type: ignore[no-untyped-call]
        )
        outcome = await DnsScanner().probe(
            "example.com", port=None, timeout_seconds=_TIMEOUT_SECONDS, credential=None
        )
        assert outcome.status == DiscoveryResultStatus.FAILURE
        assert outcome.error_message is not None
