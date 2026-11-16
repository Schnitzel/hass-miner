"""Binary sensor platform for ASIC Miner integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from pyasic_rs.data import MinerData

from .const import DOMAIN
from .coordinator import MinerCoordinator
from .entity import MinerEntity


@dataclass(frozen=True, kw_only=True)
class MinerBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[MinerData], bool | None]
    available_fn: Callable[[MinerData], bool] = lambda _: True


BINARY_SENSORS: tuple[MinerBinarySensorDescription, ...] = (
    MinerBinarySensorDescription(
        key="is_mining",
        name="Mining",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda d: d.is_mining,
    ),
    MinerBinarySensorDescription(
        key="light_flashing",
        name="Fault Light",
        value_fn=lambda d: d.light_flashing,
        available_fn=lambda d: d.light_flashing is not None,
    ),
)


class MinerBinarySensorEntity(MinerEntity, BinarySensorEntity):
    entity_description: MinerBinarySensorDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        description: MinerBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._device_unique_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success or self.coordinator.data is None:
            return False
        return self.entity_description.available_fn(self.coordinator.data)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MinerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MinerBinarySensorEntity(coordinator, desc) for desc in BINARY_SENSORS
    )
