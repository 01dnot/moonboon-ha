"""Graceful fallbacks for newer Home Assistant Bluetooth APIs.

Some of the APIs used here are recent additions. Rather than hard-failing on
an older core, degrade to something sensible.
"""

from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant


async def async_request_active_scan(hass: HomeAssistant) -> None:
    """Ask AUTO-mode scanners for a one-shot active sweep, if supported."""
    if (request := getattr(bluetooth, "async_request_active_scan", None)) is None:
        return
    try:
        await request(hass)
    except Exception:  # noqa: BLE001 - an optimisation, never fatal
        return


def reachability(hass: HomeAssistant, address: str) -> str:
    """Explain why an address cannot be reached, in human readable form."""
    diagnostics = getattr(bluetooth, "async_address_reachability_diagnostics", None)
    intent_enum = getattr(bluetooth, "BluetoothReachabilityIntent", None)
    if diagnostics is None or intent_enum is None:
        return f"{address} could not be reached"
    try:
        return diagnostics(hass, address, intent_enum.CONNECTION)
    except Exception:  # noqa: BLE001 - diagnostics must never break a flow
        return f"{address} could not be reached"
