"""Network-related field validation: hostname, IP, MAC, port, domain."""

from __future__ import annotations

import ipaddress
import re

from shared_core.validators.results import ValidationResult

_HOSTNAME_LABEL = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
_MAC_ADDRESS = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")
_DOMAIN = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z]{2,63})+$")

_MAX_HOSTNAME_LENGTH = 253
_MIN_PORT = 1
_MAX_PORT = 65_535


def validate_hostname(value: str) -> ValidationResult:
    """Validate an RFC 1123 hostname."""
    if not value or len(value) > _MAX_HOSTNAME_LENGTH:
        return ValidationResult.fail("Hostname must be between 1 and 253 characters.")
    labels = value.rstrip(".").split(".")
    if not all(_HOSTNAME_LABEL.match(label) for label in labels):
        return ValidationResult.fail(f"'{value}' is not a valid hostname.")
    return ValidationResult.ok()


def validate_ipv4(value: str) -> ValidationResult:
    """Validate an IPv4 address."""
    try:
        ipaddress.IPv4Address(value)
    except ValueError:
        return ValidationResult.fail(f"'{value}' is not a valid IPv4 address.")
    return ValidationResult.ok()


def validate_ipv6(value: str) -> ValidationResult:
    """Validate an IPv6 address."""
    try:
        ipaddress.IPv6Address(value)
    except ValueError:
        return ValidationResult.fail(f"'{value}' is not a valid IPv6 address.")
    return ValidationResult.ok()


def validate_mac_address(value: str) -> ValidationResult:
    """Validate a colon- or hyphen-delimited MAC address."""
    if not _MAC_ADDRESS.match(value):
        return ValidationResult.fail(f"'{value}' is not a valid MAC address.")
    return ValidationResult.ok()


def validate_port(value: int) -> ValidationResult:
    """Validate a TCP/UDP port number."""
    if not (_MIN_PORT <= value <= _MAX_PORT):
        return ValidationResult.fail(f"Port must be between {_MIN_PORT} and {_MAX_PORT}.")
    return ValidationResult.ok()


def validate_domain(value: str) -> ValidationResult:
    """Validate a DNS domain name (must contain at least one dot)."""
    if not _DOMAIN.match(value):
        return ValidationResult.fail(f"'{value}' is not a valid domain name.")
    return ValidationResult.ok()
