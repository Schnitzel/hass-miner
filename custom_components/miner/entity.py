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
        # Build device info from the coordinator helpers (live data first, then
        # cached profile, then None) so the device exists even when the miner is
        # unreachable at startup. Tolerate all-None: never raise here.
        mac = coordinator.device_mac
        make = coordinator.device_make
        model = coordinator.device_model
        if make or model:
            name = " ".join(p for p in (make, model) if p)
        else:
            name = f"ASIC Miner ({coordinator.ip})"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_unique_id)},
            connections=(
                {(dr.CONNECTION_NETWORK_MAC, mac)} if mac else set()
            ),
            name=name,
            manufacturer=make,
            model=model,
            sw_version=coordinator.fw_version,
            configuration_url=f"http://{coordinator.ip}",
        )

    @property
    def _device_unique_id(self) -> str:
        """Stable device identifier: prefer MAC over IP."""
        mac = self.coordinator.device_mac
        if mac:
            return mac.replace(":", "").lower()
        return self.coordinator.ip
