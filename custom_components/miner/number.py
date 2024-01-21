"""Support for Bitcoin ASIC miners."""
from __future__ import annotations

import logging

import pyasic
from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MinerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    created = set()

    @callback
    def _create_entity(key: str):
        """Create a sensor entity."""
        created.add(key)

    await coordinator.async_config_entry_first_refresh()
    if coordinator.miner.supports_autotuning:
        async_add_entities(
            [
                MinerPowerLimitNumber(
                    coordinator=coordinator,
                )
            ]
        )

    # @callback
    # def new_data_received():
    #     """Check for new sensors."""
    #     entities = [
    #         _create_entity(key) for key in coordinator.data if key not in created
    #     ]
    #     if entities:
    #         async_add_entities(entities)

    # coordinator.async_add_listener(new_data_received)


class MinerPowerLimitNumber(CoordinatorEntity[MinerCoordinator], NumberEntity):
    """Defines a Miner Number to set the Power Limit of the Miner."""

    def __init__(self, coordinator: MinerCoordinator):
        """Initialize the PowerLimit entity."""
        super().__init__(coordinator=coordinator)
        self._attr_native_value = self.coordinator.data["miner_sensors"]["power_limit"]

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.entry.title} Power Limit"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return entity.DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.data["mac"])},
            manufacturer=self.coordinator.data["make"],
            model=self.coordinator.data["model"],
            sw_version=self.coordinator.data["fw_ver"],
            name=f"{self.coordinator.entry.title}",
        )

    @property
    def unique_id(self) -> str | None:
        """Return device UUID."""
        return f"{self.coordinator.data['mac']}-power_limit"

    @property
    def native_min_value(self) -> float | None:
        """Return device minimum value."""
        return 100

    @property
    def native_max_value(self) -> float | None:
        """Return device maximum value."""
        return 5000

    @property
    def native_step(self) -> float | None:
        """Return device increment step."""
        return 100

    @property
    def native_unit_of_measurement(self):
        """Return device unit of measurement."""
        return "W"

    async def async_set_native_value(self, value):
        """Update the current value."""

        miner = self.coordinator.miner

        _LOGGER.debug(
            "%s: setting power limit to %s.", self.coordinator.entry.title, value
        )

        if not miner.supports_autotuning:
            raise TypeError(
                f"{self.coordinator.entry.title} does not support setting power limit."
            )

        result = await miner.set_power_limit(int(value))

        if not result:
            raise pyasic.APIError("Failed to set wattage.")

        self._attr_native_value = value
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data["miner_sensors"]["power_limit"] is not None:
            self._attr_native_value = self.coordinator.data["miner_sensors"][
                "power_limit"
            ]

        super()._handle_coordinator_update()
