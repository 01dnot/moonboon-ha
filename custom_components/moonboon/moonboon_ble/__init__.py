"""Client library for the Moonboon Connect 2 cradle motor."""

from .client import MoonboonClient
from .const import KNOWN_STATES, MAX_SPEED, MAX_TIMER, MIN_SPEED, MIN_TIMER
from .exceptions import (
    MoonboonCommandError,
    MoonboonError,
    MoonboonNeedsWeight,
    MoonboonNotConnected,
)
from .fade import constant, fade_out
from .models import DeviceInfo, MoonboonState, Session, Status, Step

__all__ = [
    "KNOWN_STATES",
    "MAX_SPEED",
    "MAX_TIMER",
    "MIN_SPEED",
    "MIN_TIMER",
    "DeviceInfo",
    "MoonboonClient",
    "MoonboonCommandError",
    "MoonboonError",
    "MoonboonNeedsWeight",
    "MoonboonNotConnected",
    "MoonboonState",
    "Session",
    "Status",
    "Step",
    "constant",
    "fade_out",
]
