"""Exceptions raised by the Moonboon protocol client."""

from __future__ import annotations


class MoonboonError(Exception):
    """Base class for all Moonboon errors."""


class MoonboonNotConnected(MoonboonError):
    """Raised when an operation needs a connection that is not established."""


class MoonboonCommandError(MoonboonError):
    """The motor rejected a command with a non-zero return code."""

    def __init__(self, rc: int, name: str, command: str) -> None:
        self.rc = rc
        self.command = command
        super().__init__(f"{command} failed: rc={rc} ({name})")


class MoonboonNeedsWeight(MoonboonError):
    """The motor accepted start but did not move.

    The motor has a weight sensor and refuses to rock an empty cradle. The
    official app words this as "The motor needs weight to start moving".
    """
