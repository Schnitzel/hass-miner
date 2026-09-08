"""Switch platform for ASIC Miner integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MinerCoordinator
from .entity import MinerEntity


class FaultLightSwitch(MinerEntity, SwitchEntity):
    """Controls the miner's fault/locate LED."""

    _attr_name = "Fault Light"
    _attr_icon = "mdi:led-on"

    def __init__(self, coordinator: MinerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_unique_id}_fault_light"

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.light_flashing

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self.coordinator.data.light_flashing is not None
        )

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.miner.set_fault_light(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.miner.set_fault_light(False)
        await self.coordinator.async_request_refresh()


class MiningSwitch(MinerEntity, SwitchEntity):
    """Pause or resume mining on the miner."""

    _attr_name = "Mining"
    _attr_icon = "mdi:pickaxe"

    def __init__(self, coordinator: MinerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_unique_id}_mining"

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.is_mining

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.miner.resume(timedelta(0))
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.miner.pause(timedelta(0))
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MinerCoordinator = hass.data[DOMAIN][entry.entry_id]
    miner = coordinator.miner

    entities: list[MinerEntity] = []

    # miner is None when it was unreachable at startup (the entry still loads for
    # offline resilience). Capability-gated entities can't be probed without a
    # connection, so they're skipped and appear after the first successful
    # connection + a reload.
    if miner is not None and miner.supports_set_fault_light:
        entities.append(FaultLightSwitch(coordinator))

    if miner is not None and miner.supports_pause and miner.supports_resume:
        entities.append(MiningSwitch(coordinator))

    async_add_entities(entities)
