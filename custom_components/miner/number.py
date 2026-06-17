"""Number platform for ASIC Miner integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MinerCoordinator
from .entity import MinerEntity


class PowerLimitNumber(MinerEntity, NumberEntity):
    """Set the miner's power limit in watts."""

    _attr_name = "Power Limit"
    _attr_icon = "mdi:flash"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_min_value = 1.0
    _attr_native_max_value = 10_000.0
    _attr_native_step = 10.0
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: MinerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_unique_id}_power_limit"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None:
            return None
        if data.tuning_target is not None:
            watts = data.tuning_target.watts
            if watts is not None:
                return watts
        return data.wattage

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.miner.set_power_limit(value)
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MinerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[MinerEntity] = []

    if coordinator.miner.supports_set_power_limit:
        entities.append(PowerLimitNumber(coordinator))

    async_add_entities(entities)
