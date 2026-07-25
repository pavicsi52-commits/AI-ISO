"""Fingerprint normalization.

Per docs/037 "FINGERPRINTING": Operating System, Vendor, Manufacturer,
Model, Firmware, CPU, Memory, Storage, Network Interfaces, Installed
Software, Running Services, Open Ports. Each protocol scanner's own
:attr:`~app.scanners.base.ScanOutcome.identity` uses protocol-native
key names (WMI's ``caption``/``version``, SNMP's ``sys_descr``, SSH's
``server_version``, ...); :func:`merge_fingerprint` folds every result
for one asset into this fixed, protocol-neutral shape, so
``discovery_assets.fingerprint`` always has the same key set
regardless of which protocols actually contributed data.
"""

from __future__ import annotations

from typing import Any

from app.models.enums import ProtocolType

_FINGERPRINT_FIELDS = (
    "operating_system",
    "vendor",
    "manufacturer",
    "model",
    "firmware_version",
    "cpu",
    "memory",
    "storage",
    "network_interfaces",
    "installed_software",
    "running_services",
    "open_ports",
)


def _extract_wmi(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "operating_system": identity.get("caption"),
        "vendor": "Microsoft",
        "firmware_version": identity.get("build_number"),
    }


def _extract_snmp(identity: dict[str, Any]) -> dict[str, Any]:
    return {"operating_system": identity.get("sys_descr")}


def _extract_transport_handshake(identity: dict[str, Any]) -> dict[str, Any]:
    return {"operating_system": identity.get("server_version")}


def _extract_ipmi(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "manufacturer_id": identity.get("manufacturer_id"),
        "firmware_version": identity.get("firmware_version"),
    }


def _extract_redfish(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "vendor": identity.get("vendor"),
        "model": identity.get("product"),
        "firmware_version": identity.get("redfish_version"),
    }


def _extract_bacnet(identity: dict[str, Any]) -> dict[str, Any]:
    vendor_id = identity.get("vendor_id")
    return {"vendor": str(vendor_id) if vendor_id else None}


def _extract_port_scan(identity: dict[str, Any]) -> dict[str, Any]:
    port = identity.get("port")
    return {"open_ports": [port]} if port is not None else {}


_EXTRACTORS: dict[ProtocolType, Any] = {
    ProtocolType.WMI: _extract_wmi,
    ProtocolType.SNMP: _extract_snmp,
    ProtocolType.SSH: _extract_transport_handshake,
    ProtocolType.WINRM: _extract_transport_handshake,
    ProtocolType.IPMI: _extract_ipmi,
    ProtocolType.REDFISH: _extract_redfish,
    ProtocolType.BACNET: _extract_bacnet,
    ProtocolType.TCP: _extract_port_scan,
    ProtocolType.UDP: _extract_port_scan,
}


def _extract_from_result(protocol: ProtocolType, identity: dict[str, Any]) -> dict[str, Any]:
    """Map one protocol result's own identity keys onto the fixed
    fingerprint field set.
    """
    extractor = _EXTRACTORS.get(protocol)
    return extractor(identity) if extractor is not None else {}


def merge_fingerprint(results: list[tuple[ProtocolType, dict[str, Any]]]) -> dict[str, Any]:
    """Merge every protocol result's identity data for one asset into
    one normalized fingerprint dict.

    Later results in *results* win on scalar fields; ``open_ports``
    accumulates across every TCP/UDP result instead of overwriting.
    """
    fingerprint: dict[str, Any] = dict.fromkeys(_FINGERPRINT_FIELDS)
    open_ports: list[int] = []

    for protocol, identity in results:
        extracted = _extract_from_result(protocol, identity)
        ports = extracted.pop("open_ports", None)
        if ports:
            open_ports.extend(ports)
        for key, value in extracted.items():
            if value is not None:
                fingerprint[key] = value

    if open_ports:
        fingerprint["open_ports"] = sorted(set(open_ports))
    return {key: value for key, value in fingerprint.items() if value is not None}


__all__ = ["merge_fingerprint"]
