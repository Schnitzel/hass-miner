"""Base entity for ASIC Miner integration."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MinerCoordinator


class MinerEntity(CoordinatorEntity[MinerCoordinator]):
    """Base class for all ASIC Miner entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MinerCoordinator) -> None:
        super().__init__(coordinator)
        data = coordinator.data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_unique_id)},
            connections={(dr.CONNECTION_NETWORK_MAC, data.mac)} if data.mac else set(),
            name=f"{data.device_info.make} {data.device_info.model}",
            manufacturer=data.device_info.make,
            model=data.device_info.model,
            sw_version=data.firmware_version,
            configuration_url=f"http://{coordinator.ip}",
        )

    @property
    def _device_unique_id(self) -> str:
        """Stable device identifier: prefer MAC over IP."""
        data = self.coordinator.data
        if data and data.mac:
            return data.mac.replace(":", "").lower()
        return self.coordinator.ip
