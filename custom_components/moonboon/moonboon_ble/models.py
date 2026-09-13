"""Data models for the Moonboon cradle motor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .const import STATE_RUNNING


@dataclass(frozen=True, slots=True)
class Step:
    """One step of a program: a speed held for a number of minutes."""

    speed: int
    timer: int

    def as_payload(self) -> dict[str, int]:
        return {"speed": self.speed, "timer": self.timer}

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Step:
        return cls(speed=int(data.get("speed", 0)), timer=int(data.get("timer", 0)))


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Static device information from 65/0."""

    hardware: str | None = None
    hardware_revision: str | None = None
    firmware: str | None = None
    protocol: str | None = None
    mac: str | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> DeviceInfo:
        return cls(
            hardware=data.get("hw"),
            hardware_revision=data.get("hw rev"),
            firmware=data.get("fw"),
            protocol=data.get("protocol"),
            mac=data.get("mac"),
        )


@dataclass(frozen=True, slots=True)
class Status:
    """Live status from 65/3. All durations are in seconds."""

    state: str | None = None
    duration: int = 0
    remaining: int = 0
    remaining_total: int = 0
    current_sequence: int = 0
    total_sequences: int = 0

    @property
    def is_running(self) -> bool:
        return self.state == STATE_RUNNING

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Status:
        return cls(
            state=data.get("state"),
            duration=int(data.get("duration", 0)),
            remaining=int(data.get("remaining", 0)),
            remaining_total=int(data.get("remaining total", 0)),
            current_sequence=int(data.get("current sequence", 0)),
            total_sequences=int(data.get("total sequences", 0)),
        )


@dataclass(frozen=True, slots=True)
class Session:
    """The previous run, from 65/4."""

    session_id: int | None = None
    state: str | None = None
    start_time: int | None = None
    duration: int = 0
    tempo: int = 0
    cycles: int = 0

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Session:
        return cls(
            session_id=data.get("id"),
            state=data.get("state"),
            start_time=data.get("start time"),
            duration=int(data.get("duration", 0)),
            tempo=int(data.get("tempo", 0)),
            cycles=int(data.get("cycles", 0)),
        )


@dataclass
class MoonboonState:
    """Everything the coordinator hands to the entities."""

    info: DeviceInfo = field(default_factory=DeviceInfo)
    status: Status = field(default_factory=Status)
    program: list[Step] = field(default_factory=list)
    last_session: Session = field(default_factory=Session)
    safety_stop: bool = False
    #: Computed once per poll so the value does not drift between reads.
    finishes_at: datetime | None = None

    @property
    def is_running(self) -> bool:
        return self.status.is_running

    @property
    def program_speed(self) -> int | None:
        """The speed of the first step, which is the one the user picked."""
        return self.program[0].speed if self.program else None

    @property
    def program_minutes(self) -> int | None:
        """Total programmed length in minutes."""
        if not self.program:
            return None
        return sum(step.timer for step in self.program)
