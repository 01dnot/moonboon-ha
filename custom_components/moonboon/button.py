"""Button platform: reset a stopped motor."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MoonboonConfigEntry, MoonboonCoordinator
from .entity import MoonboonEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoonboonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Moonboon buttons."""
    async_add_entities([MoonboonRestartButton(entry.runtime_data)])


class MoonboonRestartButton(MoonboonEntity, ButtonEntity):
    """Clears a stopped state so the motor can run again.

    After a safety stop the motor sits in "stopped (user)" and ignores start
    until it has been reset to "ready".
    """

    _attr_translation_key = "restart"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:restart"

    def __init__(self, coordinator: MoonboonCoordinator) -> None:
        super().__init__(coordinator, "restart")

    async def async_press(self) -> None:
        await self.coordinator.async_restart()
