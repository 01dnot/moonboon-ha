"""Select platform: which program shape to build."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_PROGRAM, PROGRAMS
from .coordinator import MoonboonConfigEntry, MoonboonCoordinator
from .entity import MoonboonEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoonboonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Moonboon program selector."""
    async_add_entities([MoonboonProgramSelect(entry.runtime_data)])


class MoonboonProgramSelect(MoonboonEntity, SelectEntity):
    """Constant speed, or the app's fade-out ramp."""

    _attr_translation_key = "program"
    _attr_options = PROGRAMS
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:chart-line-variant"

    def __init__(self, coordinator: MoonboonCoordinator) -> None:
        super().__init__(coordinator, "program")

    @property
    def current_option(self) -> str:
        return self.coordinator.program

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_option(CONF_PROGRAM, option)
