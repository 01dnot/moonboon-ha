"""Binary sensor platform: the safety stop."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MoonboonConfigEntry, MoonboonCoordinator
from .entity import MoonboonEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoonboonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Moonboon binary sensors."""
    async_add_entities([MoonboonSafetyStop(entry.runtime_data)])


class MoonboonSafetyStop(MoonboonEntity, BinarySensorEntity):
    """On when the cradle was physically held back.

    The motor pushes this the moment it happens, so it is real time rather
    than polled.
    """

    _attr_translation_key = "safety_stop"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:hand-back-left"

    def __init__(self, coordinator: MoonboonCoordinator) -> None:
        super().__init__(coordinator, "safety_stop")

    @property
    def is_on(self) -> bool | None:
        if (data := self.coordinator.data) is None:
            return None
        return data.safety_stop
