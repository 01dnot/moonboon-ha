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
from homeassistant.helpers.debounce import Debouncer
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
    RECONNECT_BACKOFF_MAX,
    SETTINGS_DEBOUNCE,
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
        self._reconnect_task: asyncio.Task[None] | None = None
        self._reconnect_attempts = 0
        #: Set when the user changed the program length, so applying uses the
        #: new length instead of preserving what was left.
        self._length_changed = False
        # Dragging a slider emits a value per step. Without this, each one
        # would restart the program over BLE.
        self._apply = Debouncer(
            hass,
            _LOGGER,
            cooldown=SETTINGS_DEBOUNCE,
            immediate=False,
            function=self._async_apply_settings,
        )

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
        """Persist a desired setting, and apply it once the user settles.

        Applying means restarting the program, because the motor cannot change
        speed in place. Sliders emit a value per step, so the actual write is
        debounced -- otherwise a drag from 20 to 80 would restart the motor
        sixty times.
        """
        options = {**self.config_entry.options, key: value}
        self.hass.config_entries.async_update_entry(
            self.config_entry, options=options
        )
        if key == CONF_MINUTES:
            self._length_changed = True
        self.async_update_listeners()
        if self.data is not None and self.data.is_running:
            await self._apply.async_call()

    async def _async_apply_settings(self) -> None:
        """Apply new settings to an already running program.

        Writing the program while the motor runs swaps it in without stopping
        the cradle -- only the countdown restarts. Changing the speed should
        therefore preserve whatever time was left, while changing the length
        obviously means to apply the new length. Going through stop/start here
        would pause the rocking for several seconds for no reason.
        """
        if self.data is None or not self.data.is_running:
            self._length_changed = False
            return
        length_changed, self._length_changed = self._length_changed, False
        try:
            await self._async_ensure_connected()
            minutes: int | None = None
            if not length_changed:
                # Read the countdown fresh rather than trusting cached data:
                # it is only polled every 30 s, and the write sets the program
                # length from it, so a stale value would stretch the session a
                # little on every change.
                status = await self._client.async_get_status()
                if not status.is_running:
                    return
                minutes = max(1, round(status.remaining / 60))
            await self._client.async_load(self.build_program(minutes))
        except MoonboonError as err:
            raise HomeAssistantError(f"Could not update the program: {err}") from err
        await self.async_request_refresh()

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
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        self._reconnect_task = self.config_entry.async_create_background_task(
            self.hass, self._async_reconnect(), f"{DOMAIN}-reconnect"
        )

    async def _async_reconnect(self) -> None:
        """Reconnect with backoff.

        An unbonded client is dropped every ~30 seconds, so a failing bond
        would otherwise make this spin.
        """
        delay = min(RECONNECT_BACKOFF_MAX, 2**self._reconnect_attempts)
        self._reconnect_attempts += 1
        await asyncio.sleep(delay)
        try:
            await self._async_ensure_connected()
        except Exception as err:  # noqa: BLE001 - the next poll retries too
            _LOGGER.debug("Reconnect failed (attempt %s): %s", self._reconnect_attempts, err)
        else:
            self._reconnect_attempts = 0

    async def async_shutdown(self) -> None:
        await self._apply.async_shutdown()
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

        self._reconnect_attempts = 0
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
        """Clear a stopped state so the motor can be started again.

        Tolerates BAD_STATE: pressing this while the motor already runs is
        harmless, not an error worth showing the user.
        """
        try:
            await self._async_ensure_connected()
            await self._client.async_restart()
        except MoonboonError as err:
            raise HomeAssistantError(f"Could not reset the motor: {err}") from err
        if self.data is not None:
            self.data.safety_stop = False
        await self.async_request_refresh()
