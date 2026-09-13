"""The Moonboon integration."""

from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .coordinator import MoonboonConfigEntry, MoonboonCoordinator

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
