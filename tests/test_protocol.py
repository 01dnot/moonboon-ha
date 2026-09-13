"""Offline tests for the Moonboon protocol layer.

These run without Home Assistant and without hardware. The expected byte
strings come from real captured traffic from the official app.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import cbor2
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "moonboon"))

from moonboon_ble.fade import constant, fade_out  # noqa: E402
from moonboon_ble.protocol import Reassembler, encode  # noqa: E402

# Captured from the iOS app: WRITE 65/1 {"command": "stop"}
CAPTURED_STOP = "0a00000e00410001a167636f6d6d616e646473746f70"
CAPTURED_START = "0a00000f00410001a167636f6d6d616e64657374617274"


def test_encode_matches_captured_stop() -> None:
    assert encode(2, 1, {"command": "stop"}, 0).hex() == CAPTURED_STOP


def test_encode_matches_captured_start() -> None:
    assert encode(2, 1, {"command": "start"}, 0).hex() == CAPTURED_START


def test_requests_use_smp_version_1() -> None:
    """The app sends version 1; the motor ignores version 0 requests."""
    raw = encode(0, 3, None, 0)
    assert (raw[0] >> 3) & 0x03 == 1


def test_round_trip() -> None:
    raw = encode(2, 1, {"command": "stop"}, 7)
    packets = Reassembler().feed(raw)
    assert len(packets) == 1
    assert packets[0].cmd == 1
    assert packets[0].seq == 7
    assert packets[0].payload == {"command": "stop"}


def test_reassembles_fragmented_frames() -> None:
    """Responses larger than the MTU arrive split across notifications."""
    raw = encode(2, 2, {"sequence": [{"speed": 20, "timer": 1}] * 12}, 3)
    reassembler = Reassembler()
    assert reassembler.feed(raw[:9]) == []
    assert reassembler.feed(raw[9:40]) == []
    packets = reassembler.feed(raw[40:])
    assert len(packets) == 1
    assert len(packets[0].payload["sequence"]) == 12


def test_decodes_push_sent_with_version_0() -> None:
    """The motor's pushes use SMP version 0 while requests use version 1."""
    body = cbor2.dumps({"rc": 0, "ur": "ustop", "state": "stopped (user)"})
    raw = struct.pack(">BBHHBB", 0x00, 0, len(body), 65, 0, 5) + body
    packets = Reassembler().feed(raw)
    assert packets[0].version == 0
    assert packets[0].cmd == 5
    assert packets[0].payload["ur"] == "ustop"


def test_two_packets_in_one_notification() -> None:
    raw = encode(0, 3, None, 1) + encode(0, 2, None, 2)
    assert len(Reassembler().feed(raw)) == 2


@pytest.mark.parametrize(
    ("speed", "minutes", "expected"),
    [
        # Captured verbatim from the app.
        (25, 120, [(25, 115), (20, 1), (16, 1), (12, 1), (8, 1), (4, 1)]),
        (13, 119, [(13, 114), (10, 1), (8, 1), (6, 1), (4, 1), (2, 1)]),
    ],
)
def test_fade_matches_app(speed, minutes, expected) -> None:
    assert [(s.speed, s.timer) for s in fade_out(speed, minutes)] == expected


def test_fade_12_step_matches_app() -> None:
    """The 12-step ramp, including its uneven-looking values."""
    steps = fade_out(20, 32, steps=12, tail=2)
    assert [s.speed for s in steps] == [20, 18, 16, 15, 13, 11, 10, 8, 6, 5, 3, 1]


def test_constant_is_a_single_step() -> None:
    assert [(s.speed, s.timer) for s in constant(40, 60)] == [(40, 60)]
