"""The Moonboon integration."""

from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import MoonboonConfigEntry, MoonboonCoordinator

_LOGGER = logging.getLogger(__name__)

def integration_version(hass: HomeAssistant) -> str:
    """Best effort lookup of the installed manifest version."""
    try:
        from homeassistant.loader import async_get_loaded_integration

        return async_get_loaded_integration(hass, DOMAIN).version or "unknown"
    except Exception:  # noqa: BLE001 - only used for logging
        return "unknown"


PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: MoonboonConfigEntry) -> bool:
    """Set up Moonboon from a config entry."""
    address = entry.unique_id
    assert address is not None

    # Logged at INFO so it is obvious which version is actually running after
    # an update -- Home Assistant caches Python modules until a full restart.
    _LOGGER.info(
        "Setting up Moonboon %s (integration version %s)",
        address,
        integration_version(hass),
    )

    if bluetooth.async_scanner_count(hass, connectable=True) == 0:
        raise ConfigEntryNotReady(
            "No Bluetooth adapter that can make outgoing connections is "
            "available. A local adapter or an ESPHome Bluetooth proxy with "
            "active connections is required."
        )

    coordinator = MoonboonCoordinator(hass, entry, address)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MoonboonConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: MoonboonConfigEntry) -> None:
    """Allow the motor to be set up again without restarting Home Assistant."""
    if entry.unique_id:
        bluetooth.async_rediscover_address(hass, entry.unique_id)


async def _async_update_listener(
    hass: HomeAssistant, entry: MoonboonConfigEntry
) -> None:
    """Push option changes out to the entities."""
    entry.runtime_data.async_update_listeners()
