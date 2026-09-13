"""Config flow for Moonboon.

Setting up requires bonding. Unbonded clients are only accepted while the
cradle is in pairing mode, and are dropped again after about 30 seconds, so
the user has to press the pairing button during setup.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
import voluptuous as vol

from .bt_compat import async_request_active_scan, reachability
from .const import DOMAIN, LOCAL_NAME
from .moonboon_ble import MoonboonClient, MoonboonError

_LOGGER = logging.getLogger(__name__)

DISCOVERY_TIMEOUT = 30


class MoonboonConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Moonboon."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._discovered: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a motor discovered over Bluetooth."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_pair()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow started from the UI."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._discovery = self._discovered[address]
            return await self.async_step_pair()

        if bluetooth.async_scanner_count(self.hass, connectable=True) == 0:
            return self.async_abort(reason="no_connectable_adapter")

        current = self._async_current_ids()
        for info in bluetooth.async_discovered_service_info(self.hass, connectable=True):
            if info.address in current or info.address in self._discovered:
                continue
            if (info.name or "").lower().startswith(LOCAL_NAME.lower()):
                self._discovered[info.address] = info

        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: f"{info.name} ({address})"
                            for address, info in self._discovered.items()
                        }
                    )
                }
            ),
        )

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to put the cradle in pairing mode, then bond."""
        assert self._discovery is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            error = await self._async_try_pair()
            if error is None:
                return self.async_create_entry(
                    title=self._discovery.name or "Moonboon",
                    data={CONF_ADDRESS: self._discovery.address},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="pair",
            data_schema=vol.Schema({}),
            description_placeholders={"name": self._discovery.name or "Moonboon"},
            errors=errors,
        )

    async def _async_try_pair(self) -> str | None:
        """Connect and bond. Returns an error key, or None on success."""
        assert self._discovery is not None
        address = self._discovery.address

        # The cradle was just put into pairing mode, so sweep now rather than
        # waiting for the next periodic discovery round.
        await async_request_active_scan(self.hass)
        try:
            await bluetooth.async_process_advertisements(
                self.hass,
                lambda _info: True,
                {"address": address, "connectable": True},
                BluetoothScanningMode.ACTIVE,
                DISCOVERY_TIMEOUT,
            )
        except TimeoutError:
            _LOGGER.debug("Motor not seen: %s", reachability(self.hass, address))
            return "not_found"

        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, address, connectable=True
        )
        if ble_device is None:
            return "not_found"

        client = MoonboonClient(DOMAIN)
        try:
            await client.connect(ble_device)
            await client.pair()
            await client.async_get_info()
        except NotImplementedError:
            # The adapter or proxy cannot bond. ESPHome proxies need firmware
            # new enough to advertise the pairing feature flag.
            return "pairing_unsupported"
        except MoonboonError:
            return "cannot_connect"
        except Exception as err:  # noqa: BLE001 - report as a pairing failure
            _LOGGER.debug("Pairing failed: %s", err)
            return "pairing_failed"
        finally:
            await client.disconnect()
        return None
