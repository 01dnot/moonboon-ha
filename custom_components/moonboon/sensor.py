"""Sensor platform: what the motor is doing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MoonboonConfigEntry, MoonboonCoordinator
from .entity import MoonboonEntity
from .moonboon_ble import KNOWN_STATES, MoonboonState


@dataclass(frozen=True, kw_only=True)
class MoonboonSensorDescription(SensorEntityDescription):
    """Describes a Moonboon sensor."""

    value_fn: Callable[[MoonboonState], str | int | datetime | None]


SENSORS: tuple[MoonboonSensorDescription, ...] = (
    MoonboonSensorDescription(
        key="state",
        translation_key="state",
        device_class=SensorDeviceClass.ENUM,
        options=KNOWN_STATES,
        icon="mdi:state-machine",
        value_fn=lambda s: s.status.state if s.status.state in KNOWN_STATES else None,
    ),
    MoonboonSensorDescription(
        key="remaining",
        translation_key="remaining",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:timer-sand",
        value_fn=lambda s: s.status.remaining,
    ),
    MoonboonSensorDescription(
        key="finishes_at",
        translation_key="finishes_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-end",
        value_fn=lambda s: s.finishes_at,
    ),
    MoonboonSensorDescription(
        key="step",
        translation_key="step",
        icon="mdi:format-list-numbered",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: (
            f"{s.status.current_sequence}/{s.status.total_sequences}"
            if s.status.total_sequences
            else None
        ),
    ),
    MoonboonSensorDescription(
        key="last_cycles",
        translation_key="last_cycles",
        state_class=SensorStateClass.TOTAL,
        icon="mdi:sine-wave",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.last_session.cycles or None,
    ),
    MoonboonSensorDescription(
        key="last_duration",
        translation_key="last_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:history",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.last_session.duration or None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoonboonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Moonboon sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        MoonboonSensor(coordinator, description) for description in SENSORS
    )


class MoonboonSensor(MoonboonEntity, SensorEntity):
    """A read-only value from the motor."""

    entity_description: MoonboonSensorDescription

    def __init__(
        self,
        coordinator: MoonboonCoordinator,
        description: MoonboonSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | datetime | None:
        if (data := self.coordinator.data) is None:
            return None
        return self.entity_description.value_fn(data)
