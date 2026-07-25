"""Tests for :class:`app.scanners.bacnet_scanner.BacnetScanner`.

No real BACnet device exists in this environment, but this scanner
hand-encodes the real BVLC/NPDU/APDU wire format directly (see its own
module docstring) rather than using a third-party stack -- so a real,
in-process fake device this test module starts itself (a plain UDP
socket that waits for the real Who-Is packet and replies with a real,
spec-correct I-Am) exercises a genuine round trip, not a simulation.
Hand-encoding that reply is what caught a real bug in the scanner's own
``_build_who_is()`` (see the fix's own comment): the BVLC length field
must cover the whole PDU including its own 4-byte header, not just the
body -- confirmed by comparing the built packet's declared length
against its real byte count.

The pure parsing function (``_parse_i_am``) is also tested directly for
every malformed-input branch a live device could never deterministically
trigger (a routed I-Am, a too-short payload, wrong PDU type).
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator

import pytest

from app.models.enums import DiscoveryResultStatus
from app.scanners.bacnet_scanner import BacnetScanner, _parse_i_am

_TIMEOUT_SECONDS = 3.0


def _build_i_am(
    *,
    device_instance: int,
    object_type: int = 8,
    max_apdu: int = 1476,
    segmentation: int = 3,
    vendor_id: int = 999,
) -> bytes:
    """Hand-encode a real, spec-correct Unconfirmed I-Am (ASHRAE 135
    clause 20.1.2), mirroring the exact tag layout ``_parse_i_am``
    expects: Object-Identifier, Max-APDU-Length-Accepted,
    Segmentation-Supported, Vendor-ID, each a real BACnet application
    tag, not a canned byte string.
    """
    npdu = bytes([0x01, 0x00])
    object_value = (object_type << 22) | device_instance
    object_id_param = bytes([0xC4]) + object_value.to_bytes(4, "big")
    max_apdu_param = bytes([0x22]) + max_apdu.to_bytes(2, "big")
    segmentation_param = bytes([0x91, segmentation])
    vendor_length = 1 if vendor_id < 256 else 2
    vendor_param = bytes([0x20 | vendor_length]) + vendor_id.to_bytes(vendor_length, "big")
    apdu = (
        bytes([0x10, 0x00]) + object_id_param + max_apdu_param + segmentation_param + vendor_param
    )
    body = npdu + apdu
    total_length = 4 + len(body)
    return bytes([0x81, 0x0B]) + total_length.to_bytes(2, "big") + body


class _FakeBacnetDevice:
    """A real UDP socket that waits for one Who-Is and replies with a
    real I-Am -- run on a background thread so the scanner's own
    blocking ``socket.recvfrom`` (itself in an executor thread) has a
    real peer to talk to.
    """

    def __init__(self, **i_am_kwargs: int) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.settimeout(_TIMEOUT_SECONDS)
        self.port = self._socket.getsockname()[1]
        self._i_am_kwargs = i_am_kwargs
        self._thread = threading.Thread(target=self._serve_once, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _serve_once(self) -> None:
        try:
            _request, peer = self._socket.recvfrom(1500)
        except TimeoutError:
            return
        self._socket.sendto(_build_i_am(**self._i_am_kwargs), peer)

    def close(self) -> None:
        self._socket.close()
        self._thread.join(timeout=_TIMEOUT_SECONDS)


@pytest.fixture
def fake_device() -> Iterator[_FakeBacnetDevice]:
    device = _FakeBacnetDevice(device_instance=1234, vendor_id=42)
    device.start()
    try:
        yield device
    finally:
        device.close()


async def test_probe_succeeds_against_real_udp_round_trip(fake_device: _FakeBacnetDevice) -> None:
    outcome = await BacnetScanner().probe(
        "127.0.0.1", port=fake_device.port, timeout_seconds=_TIMEOUT_SECONDS, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["device_instance"] == 1234
    assert outcome.identity["object_type"] == 8
    assert outcome.identity["max_apdu_length_accepted"] == 1476
    assert outcome.identity["segmentation_supported"] == 3
    assert outcome.identity["vendor_id"] == 42


async def test_probe_two_byte_vendor_id() -> None:
    device = _FakeBacnetDevice(device_instance=5, vendor_id=999)
    device.start()
    try:
        outcome = await BacnetScanner().probe(
            "127.0.0.1", port=device.port, timeout_seconds=_TIMEOUT_SECONDS, credential=None
        )
    finally:
        device.close()
    assert outcome.status == DiscoveryResultStatus.SUCCESS
    assert outcome.identity["vendor_id"] == 999


async def test_probe_silent_target_times_out() -> None:
    # A definitely-closed local UDP port produces an immediate ICMP
    # port-unreachable on this OS (a real, correct UNREACHABLE outcome,
    # not a TIMEOUT one) -- to exercise the TIMEOUT branch specifically,
    # this uses a real socket that *does* receive the Who-Is (so nothing
    # rejects the packet at the OS level) but deliberately never replies.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as silent:
        silent.bind(("127.0.0.1", 0))
        silent_port = silent.getsockname()[1]
        outcome = await BacnetScanner().probe(
            "127.0.0.1", port=silent_port, timeout_seconds=0.5, credential=None
        )
    assert outcome.status == DiscoveryResultStatus.TIMEOUT


async def test_probe_closed_port_maps_to_unreachable() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as unused:
        unused.bind(("127.0.0.1", 0))
        unused_port = unused.getsockname()[1]
    outcome = await BacnetScanner().probe(
        "127.0.0.1", port=unused_port, timeout_seconds=0.5, credential=None
    )
    assert outcome.status == DiscoveryResultStatus.UNREACHABLE


def test_parse_i_am_rejects_too_short_payload() -> None:
    assert _parse_i_am(b"\x81\x0b\x00\x04") is None


def test_parse_i_am_rejects_wrong_bvlc_type() -> None:
    payload = bytearray(_build_i_am(device_instance=1))
    payload[0] = 0x82
    assert _parse_i_am(bytes(payload)) is None


def test_parse_i_am_rejects_routed_i_am() -> None:
    payload = bytearray(_build_i_am(device_instance=1))
    payload[5] |= 0x20  # NPDU control byte: set the destination-specifier bit
    assert _parse_i_am(bytes(payload)) is None


def test_parse_i_am_rejects_wrong_apdu_service() -> None:
    payload = bytearray(_build_i_am(device_instance=1))
    payload[7] = 0x08  # Who-Is service choice instead of I-Am's 0x00
    assert _parse_i_am(bytes(payload)) is None


def test_parse_i_am_handles_missing_optional_fields() -> None:
    npdu = bytes([0x01, 0x00])
    object_id_param = bytes([0xC4]) + ((8 << 22) | 7).to_bytes(4, "big")
    apdu = bytes([0x10, 0x00]) + object_id_param
    body = npdu + apdu
    payload = bytes([0x81, 0x0B]) + (4 + len(body)).to_bytes(2, "big") + body

    parsed = _parse_i_am(payload)
    assert parsed is not None
    assert parsed["device_instance"] == 7
    assert parsed["max_apdu_length_accepted"] is None
    assert parsed["segmentation_supported"] is None
    assert parsed["vendor_id"] is None
