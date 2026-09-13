"""Async client for the Moonboon Connect 2 cradle motor.

Owns one BLE connection and speaks the vendor SMP protocol over it. It does
not reconnect on its own -- that is the coordinator's job.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .const import (
    CMD_CONTROL,
    CMD_INFO,
    CMD_LAST_SESSION,
    CMD_PROGRAM,
    CMD_PUSH,
    CMD_STATUS,
    OP_READ,
    OP_WRITE,
    RC_BAD_STATE,
    RC_NAMES,
    RC_OK,
    SMP_CHAR,
    UR_SETTINGS_CHANGED,
    UR_USER_STOP,
)
from .exceptions import (
    MoonboonCommandError,
    MoonboonNeedsWeight,
    MoonboonNotConnected,
)
from .models import DeviceInfo, MoonboonState, Session, Status, Step
from .protocol import Reassembler, encode

_LOGGER = logging.getLogger(__name__)

#: The motor accepts commands quickly; responses arrive well within this.
REQUEST_TIMEOUT = 8.0
#: HA recommends at least 10 s because BlueZ must resolve services.
CONNECT_TIMEOUT = 20.0
#: Time for the motor to actually start moving before we conclude it will not.
START_SETTLE = 1.5

PushCallback = Callable[[str, dict[str, Any]], None]


class MoonboonClient:
    """Speaks the Moonboon vendor SMP protocol over a single BLE connection."""

    def __init__(self, name: str, push_callback: PushCallback | None = None) -> None:
        self._name = name
        self._push_callback = push_callback
        self._client: BleakClient | None = None
        self._reassembler = Reassembler()
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        # Sequence 0 is reserved: the motor stamps every unsolicited push with
        # it. Using it for our own requests would make a push arriving mid
        # request be consumed as that request's reply, losing the notification
        # and answering the caller with the wrong payload.
        self._seq = 1
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ link

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def connect(
        self,
        ble_device: BLEDevice,
        disconnected_callback: Callable[[BleakClient], None] | None = None,
    ) -> None:
        """Establish a connection and subscribe to the motor's push channel."""
        self._reassembler.reset()
        # Never reuse a BleakClient between connections: HA advises against it
        # because it makes connecting less reliable.
        client = await establish_connection(
            BleakClient,
            ble_device,
            self._name,
            disconnected_callback=disconnected_callback,
            timeout=CONNECT_TIMEOUT,
        )
        self._client = client
        await client.start_notify(SMP_CHAR, self._handle_notify)

    async def pair(self) -> None:
        """Bond with the motor.

        Required for practical use: unbonded clients are only accepted while
        the cradle is in pairing mode and are dropped again after ~30 seconds.
        """
        if self._client is None:
            raise MoonboonNotConnected("Not connected")
        await self._client.pair()

    async def disconnect(self) -> None:
        client, self._client = self._client, None
        self._fail_pending(MoonboonNotConnected("Disconnected"))
        if client is not None:
            try:
                await client.disconnect()
            except Exception as err:  # noqa: BLE001 - teardown is best effort
                _LOGGER.debug("Error while disconnecting: %s", err)

    def _fail_pending(self, exc: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)
        self._pending.clear()

    # --------------------------------------------------------------- traffic

    def _handle_notify(self, _sender: Any, data: bytearray) -> None:
        for packet in self._reassembler.feed(bytes(data)):
            if packet.cmd == CMD_PUSH:
                self._dispatch_push(packet.payload)
                continue
            future = self._pending.pop(packet.seq, None)
            if future is not None and not future.done():
                future.set_result(packet.payload)

    def _dispatch_push(self, payload: dict[str, Any]) -> None:
        _LOGGER.debug("Unsolicited message from the motor: %s", payload)
        code = payload.get("ur")
        if code not in (UR_SETTINGS_CHANGED, UR_USER_STOP):
            _LOGGER.debug("Unknown unsolicited code %r: %s", code, payload)
        if self._push_callback is not None and isinstance(code, str):
            self._push_callback(code, payload)

    async def _request(
        self, op: int, cmd: int, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if self._client is None or not self._client.is_connected:
            raise MoonboonNotConnected("Not connected to the motor")
        async with self._lock:
            seq = self._seq
            self._seq = self._seq % 255 + 1  # 1..255, never 0
            future: asyncio.Future[dict[str, Any]] = (
                asyncio.get_running_loop().create_future()
            )
            self._pending[seq] = future
            try:
                await self._client.write_gatt_char(
                    SMP_CHAR, encode(op, cmd, payload, seq), response=False
                )
                return await asyncio.wait_for(future, REQUEST_TIMEOUT)
            finally:
                self._pending.pop(seq, None)

    @staticmethod
    def _check(payload: dict[str, Any], command: str, *, allow: tuple[int, ...] = ()) -> None:
        rc = payload.get("rc", RC_OK)
        if rc == RC_OK or rc in allow:
            return
        raise MoonboonCommandError(rc, RC_NAMES.get(rc, "?"), command)

    # ----------------------------------------------------------------- reads

    async def async_get_info(self) -> DeviceInfo:
        payload = await self._request(OP_READ, CMD_INFO)
        self._check(payload, "info")
        return DeviceInfo.from_payload(payload)

    async def async_get_status(self) -> Status:
        payload = await self._request(OP_READ, CMD_STATUS)
        self._check(payload, "status")
        return Status.from_payload(payload)

    async def async_get_program(self) -> list[Step]:
        payload = await self._request(OP_READ, CMD_PROGRAM)
        self._check(payload, "program")
        sequence = payload.get("sequence") or []
        return [Step.from_payload(item) for item in sequence]

    async def async_get_last_session(self) -> Session:
        payload = await self._request(OP_READ, CMD_LAST_SESSION)
        self._check(payload, "last session")
        return Session.from_payload(payload)

    async def async_get_state(self) -> MoonboonState:
        """Read everything the entities need in one pass."""
        return MoonboonState(
            info=await self.async_get_info(),
            status=await self.async_get_status(),
            program=await self.async_get_program(),
            last_session=await self.async_get_last_session(),
        )

    # ---------------------------------------------------------------- writes

    async def async_restart(self) -> None:
        """Clear a stopped state, moving the motor to "ready".

        This is the step that is easy to miss: `start` only works from
        "ready" (or "awaiting input"). Without it the motor answers rc:0 and
        does nothing.

        BAD_STATE means the motor is already running, or already reset, so it
        is tolerated -- the caller only wants it in a startable state.
        """
        payload = await self._request(OP_WRITE, CMD_CONTROL, {"command": "restart"})
        self._check(payload, "restart", allow=(RC_BAD_STATE,))

    async def async_stop(self) -> None:
        """Stop rocking.

        BAD_STATE means it was already stopped, which is not an error.
        """
        payload = await self._request(OP_WRITE, CMD_CONTROL, {"command": "stop"})
        self._check(payload, "stop", allow=(RC_BAD_STATE,))

    async def async_load(self, program: list[Step]) -> None:
        """Upload a program. `time now` is sent exactly as the app does."""
        payload = await self._request(
            OP_WRITE,
            CMD_PROGRAM,
            {
                "sequence": [step.as_payload() for step in program],
                "time now": int(time.time() * 1000),
            },
        )
        self._check(payload, "load program")

    async def async_start(self) -> None:
        payload = await self._request(OP_WRITE, CMD_CONTROL, {"command": "start"})
        self._check(payload, "start")

    async def async_play(self, program: list[Step]) -> Status:
        """Run a program, using whichever handshake the current state needs.

        The official app uses two patterns, and which one is valid depends on
        what the motor is doing:

        * running  -> stop, which leaves it in "awaiting input"
        * stopped  -> restart, which leaves it in "ready"

        Sending the wrong one returns rc:6 (BAD_STATE), so the state is read
        first. Then the program is loaded and started.

        A zero return code does not mean the motor moved: it refuses to rock
        an empty cradle and reports success either way, so the result is
        verified.
        """
        status = await self.async_get_status()
        if status.is_running:
            await self.async_stop()
        else:
            await self.async_restart()
        await asyncio.sleep(0.3)
        await self.async_load(program)
        await self.async_start()
        await asyncio.sleep(START_SETTLE)
        status = await self.async_get_status()
        if not status.is_running:
            raise MoonboonNeedsWeight(
                "The motor accepted the command but did not start. "
                "It has a weight sensor and will not rock an empty cradle."
            )
        return status
