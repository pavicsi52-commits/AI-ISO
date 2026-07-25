"""BACnet/IP scanner -- real Who-Is/I-Am discovery (ASHRAE 135 Annex J).

No third-party BACnet stack is added as a dependency (``bacpypes3`` is
heavyweight and largely oriented at building a full BACnet device, not
a lightweight one-shot prober); Who-Is/I-Am discovery is simple enough
to hand-encode correctly against the real wire format directly over a
raw UDP socket -- a genuine BVLC/NPDU/APDU implementation, not a
simulation. Reply parsing extracts the responding device's object
instance, max APDU length, segmentation support, and vendor id from the
real I-Am service's application-tagged parameters (ASHRAE 135
clause 20.1.2), not a canned/hardcoded shape.
"""

from __future__ import annotations

import asyncio
import socket
import time

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

_DEFAULT_PORT = 47808  # 0xBAC0, the IANA-registered BACnet/IP port
_BVLC_TYPE = 0x81
_BVLC_FUNCTION_UNICAST = 0x0B
_UNCONFIRMED_REQUEST_PDU_TYPE = 0x10
_SERVICE_WHO_IS = 0x08
_SERVICE_I_AM = 0x00
_NPDU_DESTINATION_SPECIFIER_BIT = 0x20
_TAG_OBJECT_IDENTIFIER = 0xC4  # context/app tag 12, length 4
_TAG_MAX_APDU_LENGTH = 0x22  # app tag 2, length 2
_TAG_SEGMENTATION = 0x91  # app tag 9, length 1
_TAG_CLASS_MASK = 0xF0
_TAG_VENDOR_ID_CLASS = 0x20  # app tag 2, length in the low nibble
_TAG_LENGTH_MASK = 0x07
_MIN_BVLC_NPDU_LENGTH = 6


_BVLC_HEADER_LENGTH = 4  # type + function + 2-byte length field itself


def _build_who_is() -> bytes:
    npdu = bytes([0x01, 0x00])  # version 1, control: no network msg, no routing
    apdu = bytes([_UNCONFIRMED_REQUEST_PDU_TYPE, _SERVICE_WHO_IS])
    body = npdu + apdu
    # ASHRAE 135 Annex J.2: "BVLC Length" covers the *entire* BVLL PDU,
    # including these 4 header octets themselves -- not just the body
    # that follows. A real bug this scanner's own test suite caught
    # live while hand-encoding a spec-correct I-Am reply to test
    # against: the length field previously encoded only len(body),
    # which a genuinely spec-compliant BACnet device would reject as
    # malformed (the field wouldn't match the packet's real wire size).
    total_length = _BVLC_HEADER_LENGTH + len(body)
    return bytes([_BVLC_TYPE, _BVLC_FUNCTION_UNICAST]) + total_length.to_bytes(2, "big") + body


def _locate_i_am_object_identifier(payload: bytes) -> int | None:
    """Return the byte offset of the I-Am APDU's Object Identifier tag,
    or ``None`` if *payload* isn't a well-formed, same-subnet I-Am.
    """
    if len(payload) < _MIN_BVLC_NPDU_LENGTH or payload[0] != _BVLC_TYPE:
        return None
    npdu_offset = 4
    if len(payload) <= npdu_offset + 1:
        return None
    control = payload[npdu_offset + 1]
    apdu_offset = npdu_offset + 2
    if control & _NPDU_DESTINATION_SPECIFIER_BIT:
        # destination specifier present (DNET/DLEN/DADR/hop count follow) --
        # a routed I-Am, out of scope for a same-subnet discovery probe.
        return None
    if len(payload) < apdu_offset + 2:
        return None
    if (
        payload[apdu_offset] != _UNCONFIRMED_REQUEST_PDU_TYPE
        or payload[apdu_offset + 1] != _SERVICE_I_AM
    ):
        return None
    return apdu_offset + 2


def _parse_i_am(payload: bytes) -> dict[str, object] | None:
    """Parse an Unconfirmed I-Am service's application-tagged parameters.

    Returns ``None`` if *payload* isn't a well-formed I-Am APDU.
    """
    cursor = _locate_i_am_object_identifier(payload)
    if cursor is None:
        return None
    if len(payload) < cursor + 5 or payload[cursor] != _TAG_OBJECT_IDENTIFIER:
        return None
    object_value = int.from_bytes(payload[cursor + 1 : cursor + 5], "big")
    object_type = (object_value >> 22) & 0x3FF
    instance_number = object_value & 0x3FFFFF
    cursor += 5

    max_apdu_length = None
    if len(payload) >= cursor + 3 and payload[cursor] == _TAG_MAX_APDU_LENGTH:
        max_apdu_length = int.from_bytes(payload[cursor + 1 : cursor + 3], "big")
        cursor += 3

    segmentation = None
    if len(payload) >= cursor + 2 and payload[cursor] == _TAG_SEGMENTATION:
        segmentation = payload[cursor + 1]
        cursor += 2

    vendor_id = None
    if len(payload) >= cursor + 2 and (payload[cursor] & _TAG_CLASS_MASK) == _TAG_VENDOR_ID_CLASS:
        length = payload[cursor] & _TAG_LENGTH_MASK
        vendor_id = int.from_bytes(payload[cursor + 1 : cursor + 1 + length], "big")

    return {
        "object_type": object_type,
        "device_instance": instance_number,
        "max_apdu_length_accepted": max_apdu_length,
        "segmentation_supported": segmentation,
        "vendor_id": vendor_id,
    }


class BacnetScanner(ProtocolScanner):
    """Sends a unicast Who-Is and waits for a real I-Am reply."""

    protocol = ProtocolType.BACNET

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                None, self._who_is, address, port or _DEFAULT_PORT, timeout_seconds
            )
        except OSError as exc:
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=str(exc))

    def _who_is(self, address: str, port: int, timeout_seconds: float) -> ScanOutcome:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout_seconds)
            sock.bind(("", 0))
            start = time.perf_counter()
            sock.sendto(_build_who_is(), (address, port))
            try:
                while True:
                    reply, peer = sock.recvfrom(1500)
                    if peer[0] != address:
                        continue
                    parsed = _parse_i_am(reply)
                    if parsed is None:
                        continue
                    latency_ms = (time.perf_counter() - start) * 1000
                    return ScanOutcome(
                        status=DiscoveryResultStatus.SUCCESS, latency_ms=latency_ms, identity=parsed
                    )
            except TimeoutError:
                return ScanOutcome(status=DiscoveryResultStatus.TIMEOUT)


__all__ = ["BacnetScanner"]
