"""Switch platform: the main on/off control for the cradle."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MoonboonConfigEntry, MoonboonCoordinator
from .entity import MoonboonEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoonboonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Moonboon switch."""
    async_add_entities([MoonboonSwitch(entry.runtime_data)])


class MoonboonSwitch(MoonboonEntity, SwitchEntity):
    """Starts and stops the rocking.

    Deliberately a switch rather than a fan: Home Assistant defines a fan as a
    device controlling the vectors of a fan, which a cradle is not. Users who
    want a percentage slider can convert this with the switch_as_x helper.
    """

    _attr_name = None
    _attr_icon = "mdi:cradle"

    def __init__(self, coordinator: MoonboonCoordinator) -> None:
        super().__init__(coordinator, "switch")

    @property
    def is_on(self) -> bool | None:
        if (data := self.coordinator.data) is None:
            return None
        return data.is_running

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if (data := self.coordinator.data) is None:
            return None
        return {
            "motor_state": data.status.state,
            "program": [step.as_payload() for step in data.program],
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_play()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_stop()
