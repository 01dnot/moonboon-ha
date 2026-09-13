"""Protocol constants for the Moonboon Connect 2 cradle motor."""

from __future__ import annotations

from typing import Final

SMP_SERVICE: Final = "8d53dc1d-1db7-4cd3-868b-8a527460aa84"
SMP_CHAR: Final = "da2e7828-fbce-4e01-ae9e-261174997c48"

#: Vendor-specific MCUmgr group used for motor control.
GROUP: Final = 65

#: The official app sends every request with SMP version 1. The motor's own
#: unsolicited pushes come back with version 0, so never validate on receive.
VERSION: Final = 1

OP_READ: Final = 0
OP_READ_RSP: Final = 1
OP_WRITE: Final = 2
OP_WRITE_RSP: Final = 3

CMD_INFO: Final = 0
CMD_CONTROL: Final = 1
CMD_PROGRAM: Final = 2
CMD_STATUS: Final = 3
CMD_LAST_SESSION: Final = 4
CMD_PUSH: Final = 5

RC_OK: Final = 0
RC_INVALID_ARG: Final = 3
RC_BAD_STATE: Final = 6
RC_NOT_SUPPORTED: Final = 8

RC_NAMES: Final = {
    0: "OK",
    1: "UNKNOWN",
    2: "NOMEM",
    3: "INVALID_ARG",
    4: "TIMEOUT",
    5: "NOENT",
    6: "BAD_STATE",
    7: "MSG_TOO_LONG",
    8: "NOT_SUPPORTED",
    9: "BUSY",
}

STATE_RUNNING: Final = "running"
STATE_READY: Final = "ready"
STATE_AWAITING_INPUT: Final = "awaiting input"

#: Every state string the motor is known to report.
KNOWN_STATES: Final = [
    "running",
    "paused",
    "idle",
    "finished",
    "ready",
    "awaiting input",
    "stopped (user)",
    "stopped (app)",
    "stopped (timeout)",
    "stopped (error)",
]

#: Confirmed unsolicited push codes. Both fire only on physical interaction
#: with the cradle -- the motor announces nothing else, not even program end.
UR_SETTINGS_CHANGED: Final = "pot"
UR_USER_STOP: Final = "ustop"

MAX_SPEED: Final = 100
MIN_SPEED: Final = 1
MAX_TIMER: Final = 720
MIN_TIMER: Final = 1
