"""Number platform: rocking speed and program length."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_MINUTES, CONF_SPEED
from .coordinator import MoonboonConfigEntry, MoonboonCoordinator
from .entity import MoonboonEntity
from .moonboon_ble import MAX_SPEED, MAX_TIMER, MIN_SPEED, MIN_TIMER


@dataclass(frozen=True, kw_only=True)
class MoonboonNumberDescription(NumberEntityDescription):
    """Describes a Moonboon number entity."""

    option_key: str
    value_fn: Callable[[MoonboonCoordinator], float | None]


NUMBERS: tuple[MoonboonNumberDescription, ...] = (
    MoonboonNumberDescription(
        key="speed",
        translation_key="speed",
        option_key=CONF_SPEED,
        native_min_value=MIN_SPEED,
        native_max_value=MAX_SPEED,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        icon="mdi:speedometer",
        value_fn=lambda c: c.speed,
    ),
    MoonboonNumberDescription(
        key="minutes",
        translation_key="minutes",
        option_key=CONF_MINUTES,
        native_min_value=MIN_TIMER,
        native_max_value=MAX_TIMER,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        mode=NumberMode.BOX,
        icon="mdi:timer-outline",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda c: c.minutes,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoonboonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Moonboon numbers."""
    coordinator = entry.runtime_data
    async_add_entities(
        MoonboonNumber(coordinator, description) for description in NUMBERS
    )


class MoonboonNumber(MoonboonEntity, NumberEntity):
    """A setting that shapes the next program."""

    entity_description: MoonboonNumberDescription

    def __init__(
        self,
        coordinator: MoonboonCoordinator,
        description: MoonboonNumberDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_option(
            self.entity_description.option_key, int(value)
        )
