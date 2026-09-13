"""Diagnostics for Moonboon.

Diagnostics downloads routinely get pasted into public issue reports, so the
device address is redacted everywhere it appears -- including inside the
free-text reachability explanation.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .bt_compat import reachability
from .coordinator import MoonboonConfigEntry

REDACTED = "**REDACTED**"
TO_REDACT = {"mac", "address", "source", "unique_id"}


def _scrub(text: str, *secrets: str | None) -> str:
    """Remove addresses from a human readable string."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
            text = text.replace(secret.lower(), REDACTED)
            text = text.replace(secret.upper(), REDACTED)
    return text


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
        }
        for device in bluetooth.async_scanner_devices_by_address(
            hass, address, connectable=True
        )
    ]

    state: dict[str, Any] = {}
    if coordinator.data is not None:
        state = {
            "info": asdict(coordinator.data.info),
            "status": asdict(coordinator.data.status),
            "program": [step.as_payload() for step in coordinator.data.program],
            "last_session": asdict(coordinator.data.last_session),
            "safety_stop": coordinator.data.safety_stop,
        }

    return async_redact_data(
        {
            "options": dict(entry.options),
            "scanner_count": bluetooth.async_scanner_count(hass, connectable=True),
            "scanners_seeing_device": scanners,
            "reachability": _scrub(reachability(hass, address), address),
            "state": state,
        },
        TO_REDACT,
    )
