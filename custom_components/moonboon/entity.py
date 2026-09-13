"""Base entity for Moonboon."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MoonboonCoordinator


class MoonboonEntity(CoordinatorEntity[MoonboonCoordinator]):
    """Common device info and availability for all Moonboon entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MoonboonCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_{key}"
        info = coordinator.data.info if coordinator.data else None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer="Moonboon",
            model=info.hardware if info else None,
            hw_version=info.hardware_revision if info else None,
            sw_version=info.firmware if info else None,
            name="Moonboon",
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None
