"""SMP framing and CBOR codec for the Moonboon vendor group.

The motor speaks MCUmgr SMP over BLE: an 8-byte header followed by a CBOR
body. Motor control lives in vendor group 65.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

import cbor2

from .const import GROUP, VERSION

_HEADER = struct.Struct(">BBHHBB")
HEADER_LEN = 8


@dataclass(frozen=True, slots=True)
class Packet:
    """A decoded SMP packet."""

    op: int
    version: int
    group: int
    seq: int
    cmd: int
    payload: dict[str, Any]


def encode(op: int, cmd: int, payload: dict[str, Any] | None, seq: int) -> bytes:
    """Build an SMP request for the motor's vendor group."""
    body = cbor2.dumps(payload if payload is not None else {})
    header = _HEADER.pack(op | (VERSION << 3), 0, len(body), GROUP, seq, cmd)
    return header + body


def decode(raw: bytes) -> Packet | None:
    """Decode one SMP packet, or None if the body is not valid CBOR.

    The version field is deliberately not validated: requests go out as
    version 1 but the motor's pushes come back as version 0.
    """
    if len(raw) < HEADER_LEN:
        return None
    op_byte, _flags, length, group, seq, cmd = _HEADER.unpack(raw[:HEADER_LEN])
    body = raw[HEADER_LEN : HEADER_LEN + length]
    if len(body) < length:
        return None
    try:
        payload = cbor2.loads(body) if length else {}
    except Exception:  # noqa: BLE001 - malformed frames are simply dropped
        return None
    if not isinstance(payload, dict):
        return None
    return Packet(
        op=op_byte & 0x07,
        version=(op_byte >> 3) & 0x03,
        group=group,
        seq=seq,
        cmd=cmd,
        payload=payload,
    )


def body_length(raw: bytes) -> int | None:
    """Return the declared body length of a (possibly partial) frame."""
    if len(raw) < HEADER_LEN:
        return None
    return struct.unpack(">H", raw[2:4])[0]


class Reassembler:
    """Reassembles notification fragments into whole SMP packets.

    Responses larger than the MTU arrive split across several notifications,
    so frames must be buffered until the declared body length is present.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Packet]:
        """Add received bytes and return any packets that are now complete."""
        self._buf += data
        packets: list[Packet] = []
        while len(self._buf) >= HEADER_LEN:
            length = struct.unpack(">H", self._buf[2:4])[0]
            total = HEADER_LEN + length
            if len(self._buf) < total:
                break
            raw = bytes(self._buf[:total])
            del self._buf[:total]
            if (packet := decode(raw)) is not None:
                packets.append(packet)
        return packets

    def reset(self) -> None:
        """Drop any partial frame, e.g. after a reconnect."""
        self._buf.clear()
