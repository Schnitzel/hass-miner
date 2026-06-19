"""Number platform for ASIC Miner integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import vnish
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


class VnishThrottleNumber(MinerEntity, NumberEntity):
    """[BETA] Set the VNish throttle (percent of full power).

    asic-rs is read-only for VNish power, so this drives the VNish REST API
    directly (see vnish.py). Replace once asic-rs supports VNish writes.
    """

    _attr_name = "VNish Throttle"
    _attr_icon = "mdi:speedometer-slow"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = float(vnish.THROTTLE_MIN)
    _attr_native_max_value = float(vnish.THROTTLE_MAX)
    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: MinerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_unique_id}_vnish_throttle"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.vnish_throttle

    async def async_set_native_value(self, value: float) -> None:
        session = async_get_clientsession(self.hass)
        ok, msg = await vnish.set_throttle(
            session, self.coordinator.ip, self.coordinator.password, int(value)
        )
        if ok:
            self.coordinator.vnish_throttle = int(value)
            self.async_write_ha_state()
        else:
            raise RuntimeError(f"VNish throttle {int(value)}% failed: {msg}")
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MinerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[MinerEntity] = []

    # Native PowerLimit is gated on a miner capability flag. When the miner is
    # None (offline at startup) we cannot know it, so we skip the native entity;
    # it appears after the first successful connection + a reload.
    if (
        coordinator.miner is not None
        and coordinator.miner.supports_set_power_limit
    ):
        entities.append(PowerLimitNumber(coordinator))

    # BETA: VNish throttle for VNish-firmware miners (asic-rs read-only here).
    # VNish detection falls back to the cached profile when offline at startup.
    is_vnish = coordinator.is_vnish or bool(
        coordinator.profile and coordinator.profile.get("is_vnish")
    )
    if is_vnish:
        entities.append(VnishThrottleNumber(coordinator))

    async_add_entities(entities)
