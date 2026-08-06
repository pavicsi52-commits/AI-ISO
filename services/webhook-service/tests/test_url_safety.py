"""Pure tests for app/security/url_safety.py -- no database, no fixtures.

Real DNS resolution throughout -- no mocking. `example.com` is IANA-reserved
for exactly this kind of testing use and always resolves to a genuine public
IP; `.invalid` is an IANA-reserved TLD guaranteed never to resolve, so the
unresolvable-host assertion cannot flake.
"""

from __future__ import annotations

import pytest
from shared_core.exceptions.validation import ValidationError

from app.security.url_safety import assert_safe_url, is_public_address, resolve_hostname, validate_scheme


class TestValidateScheme:
    def test_http_is_allowed(self) -> None:
        validate_scheme("http://example.com")

    def test_https_is_allowed(self) -> None:
        validate_scheme("https://example.com")

    def test_scheme_matching_is_case_insensitive(self) -> None:
        validate_scheme("HTTP://example.com")

    def test_ftp_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_scheme("ftp://example.com")

    def test_websocket_scheme_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_scheme("ws://example.com")

    def test_a_schemeless_url_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_scheme("example.com/path")


class TestIsPublicAddress:
    def test_a_public_ipv4_address_is_public(self) -> None:
        assert is_public_address("8.8.8.8") is True

    def test_a_public_ipv6_address_is_public(self) -> None:
        assert is_public_address("2001:4860:4860::8888") is True

    def test_a_private_ipv4_address_is_not_public(self) -> None:
        assert is_public_address("10.0.0.5") is False

    def test_another_private_ipv4_range_is_not_public(self) -> None:
        assert is_public_address("192.168.1.1") is False

    def test_ipv4_loopback_is_not_public(self) -> None:
        assert is_public_address("127.0.0.1") is False

    def test_ipv6_loopback_is_not_public(self) -> None:
        assert is_public_address("::1") is False

    def test_link_local_is_not_public(self) -> None:
        assert is_public_address("169.254.169.254") is False

    def test_multicast_is_not_public(self) -> None:
        assert is_public_address("224.0.0.1") is False

    def test_reserved_is_not_public(self) -> None:
        assert is_public_address("240.0.0.1") is False

    def test_unspecified_is_not_public(self) -> None:
        assert is_public_address("0.0.0.0") is False


class TestResolveHostname:
    async def test_resolves_a_real_hostname_to_at_least_one_address(self) -> None:
        addresses = await resolve_hostname("example.com")
        assert len(addresses) >= 1

    async def test_localhost_resolves_to_a_loopback_address(self) -> None:
        addresses = await resolve_hostname("localhost")
        assert any(is_public_address(ip) is False for ip in addresses)

    async def test_an_unresolvable_host_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            await resolve_hostname("this-should-not-resolve.invalid")


class TestAssertSafeUrl:
    async def test_a_genuinely_public_hostname_is_accepted(self) -> None:
        await assert_safe_url("http://example.com")

    async def test_a_genuinely_public_ip_literal_is_accepted(self) -> None:
        await assert_safe_url("http://93.184.216.34")

    async def test_a_direct_link_local_ip_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            await assert_safe_url("http://169.254.169.254/")

    async def test_a_direct_loopback_ip_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            await assert_safe_url("http://127.0.0.1/")

    async def test_a_hostname_that_resolves_to_loopback_is_rejected(self) -> None:
        # Distinct code path from the direct-IP cases above: the rejection only happens
        # after DNS resolution turns "localhost" into a loopback address.
        with pytest.raises(ValidationError):
            await assert_safe_url("http://localhost/")

    async def test_an_unsafe_scheme_is_rejected_before_any_dns_resolution(self) -> None:
        with pytest.raises(ValidationError):
            await assert_safe_url("ftp://example.com")

    async def test_a_url_with_no_host_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            await assert_safe_url("http://")

    async def test_an_unresolvable_host_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            await assert_safe_url("http://this-should-not-resolve.invalid/")
