"""Diagnostics for Moonboon."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .bt_compat import reachability
from .coordinator import MoonboonConfigEntry

TO_REDACT = {"mac"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MoonboonConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    address = coordinator.address

    scanners = [
        {
            "source": device.scanner.source if device.scanner else None,
            "rssi": device.advertisement.rssi if device.advertisement else None,
            "connectable": True,
        }
        for device in bluetooth.async_scanner_devices_by_address(
            hass, address, connectable=True
        )
    ]

    data: dict[str, Any] = {}
    if coordinator.data is not None:
        data = {
            "info": {
                key: value
                for key, value in asdict(coordinator.data.info).items()
                if key not in TO_REDACT
            },
            "status": asdict(coordinator.data.status),
            "program": [step.as_payload() for step in coordinator.data.program],
            "last_session": asdict(coordinator.data.last_session),
            "safety_stop": coordinator.data.safety_stop,
        }

    return {
        "options": dict(entry.options),
        "scanner_count": bluetooth.async_scanner_count(hass, connectable=True),
        "scanners_seeing_device": scanners,
        "reachability": reachability(hass, address),
        "state": data,
    }
