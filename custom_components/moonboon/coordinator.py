"""Connection handling and polling for the Moonboon cradle motor."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from bleak import BleakClient
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .bt_compat import reachability

from .const import (
    CONF_MINUTES,
    CONF_PROGRAM,
    CONF_SPEED,
    DEFAULT_MINUTES,
    DEFAULT_PROGRAM,
    DEFAULT_SPEED,
    DOMAIN,
    PROGRAM_FADE,
    UPDATE_INTERVAL_IDLE,
    UPDATE_INTERVAL_RUNNING,
)
from .moonboon_ble import (
    MoonboonClient,
    MoonboonError,
    MoonboonNeedsWeight,
    MoonboonState,
    Step,
    constant,
    fade_out,
)
from .moonboon_ble.const import UR_SETTINGS_CHANGED, UR_USER_STOP

_LOGGER = logging.getLogger(__name__)

type MoonboonConfigEntry = ConfigEntry["MoonboonCoordinator"]


class MoonboonCoordinator(DataUpdateCoordinator[MoonboonState]):
    """Keeps one connection to the motor and feeds the entities."""

    config_entry: MoonboonConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: MoonboonConfigEntry, address: str
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_IDLE),
        )
        self.address = address
        self._client = MoonboonClient(DOMAIN, push_callback=self._handle_push)
        self._connect_lock = asyncio.Lock()

    # ------------------------------------------------------------- settings

    def _option(self, key: str, default: Any) -> Any:
        return self.config_entry.options.get(key, default)

    @property
    def speed(self) -> int:
        return int(self._option(CONF_SPEED, DEFAULT_SPEED))

    @property
    def minutes(self) -> int:
        return int(self._option(CONF_MINUTES, DEFAULT_MINUTES))

    @property
    def program(self) -> str:
        return str(self._option(CONF_PROGRAM, DEFAULT_PROGRAM))

    async def async_set_option(self, key: str, value: Any) -> None:
        """Persist a desired setting and apply it if the motor is running."""
        options = {**self.config_entry.options, key: value}
        self.hass.config_entries.async_update_entry(
            self.config_entry, options=options
        )
        if self.data is not None and self.data.is_running:
            # Restart with the new settings, keeping roughly the time that is
            # left rather than silently extending the session.
            remaining = max(1, round(self.data.status.remaining / 60))
            await self.async_play(minutes_override=remaining)
        else:
            self.async_update_listeners()

    def build_program(self, minutes_override: int | None = None) -> list[Step]:
        minutes = minutes_override if minutes_override is not None else self.minutes
        if self.program == PROGRAM_FADE:
            return fade_out(self.speed, minutes)
        return constant(self.speed, minutes)

    # ---------------------------------------------------------------- link

    async def _async_ensure_connected(self) -> None:
        if self._client.is_connected:
            return
        async with self._connect_lock:
            if self._client.is_connected:
                return
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                raise UpdateFailed(self._unreachable_reason())
            await self._client.connect(
                ble_device, disconnected_callback=self._handle_disconnect
            )

    def _unreachable_reason(self) -> str:
        """Ask the Bluetooth stack why the motor cannot be reached."""
        return reachability(self.hass, self.address)

    @callback
    def _handle_disconnect(self, _client: BleakClient) -> None:
        _LOGGER.debug("Disconnected from %s", self.address)
        self.hass.async_create_task(self._async_reconnect_soon())

    async def _async_reconnect_soon(self) -> None:
        await asyncio.sleep(1)
        try:
            await self._async_ensure_connected()
        except Exception as err:  # noqa: BLE001 - the next poll will retry
            _LOGGER.debug("Reconnect failed, will retry on next update: %s", err)

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self._client.disconnect()

    # --------------------------------------------------------------- pushes

    @callback
    def _handle_push(self, code: str, payload: dict[str, Any]) -> None:
        """Handle an unsolicited message.

        The motor only pushes when a human touches the cradle: settings
        changed at the device, or the cradle held back.
        """
        if self.data is None:
            return
        state = self.data
        if code == UR_USER_STOP:
            state.safety_stop = True
        elif code == UR_SETTINGS_CHANGED:
            state.safety_stop = False
        self.async_set_updated_data(state)
        # The push carries new settings but not the countdown, so refresh.
        self.hass.async_create_task(self.async_request_refresh())

    # --------------------------------------------------------------- polling

    async def _async_update_data(self) -> MoonboonState:
        try:
            await self._async_ensure_connected()
            state = await self._client.async_get_state()
        except UpdateFailed:
            raise
        except MoonboonError as err:
            raise UpdateFailed(f"Error talking to the motor: {err}") from err
        except Exception as err:  # noqa: BLE001 - surface as a normal failure
            raise UpdateFailed(f"Error talking to the motor: {err}") from err

        if self.data is not None:
            state.safety_stop = self.data.safety_stop and not state.is_running
        if state.is_running and state.status.remaining > 0:
            # Computed here, once, so the sensor does not drift between reads.
            state.finishes_at = dt_util.utcnow() + timedelta(
                seconds=state.status.remaining
            )

        interval = (
            UPDATE_INTERVAL_RUNNING if state.is_running else UPDATE_INTERVAL_IDLE
        )
        if self.update_interval != timedelta(seconds=interval):
            self.update_interval = timedelta(seconds=interval)
        return state

    # -------------------------------------------------------------- commands

    async def async_play(self, minutes_override: int | None = None) -> None:
        """Start rocking using the current settings."""
        program = self.build_program(minutes_override)
        try:
            await self._async_ensure_connected()
            await self._client.async_play(program)
        except MoonboonNeedsWeight as err:
            raise HomeAssistantError(
                "The motor did not start. It has a weight sensor and will not "
                "rock an empty cradle."
            ) from err
        except MoonboonError as err:
            raise HomeAssistantError(f"Could not start the motor: {err}") from err
        if self.data is not None:
            self.data.safety_stop = False
        await self.async_request_refresh()

    async def async_stop(self) -> None:
        try:
            await self._async_ensure_connected()
            await self._client.async_stop()
        except MoonboonError as err:
            raise HomeAssistantError(f"Could not stop the motor: {err}") from err
        await self.async_request_refresh()

    async def async_restart(self) -> None:
        """Clear a stopped state so the motor can be started again."""
        try:
            await self._async_ensure_connected()
            await self._client.async_restart()
        except MoonboonError as err:
            raise HomeAssistantError(f"Could not reset the motor: {err}") from err
        if self.data is not None:
            self.data.safety_stop = False
        await self.async_request_refresh()
