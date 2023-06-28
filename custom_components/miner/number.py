"""Support for IoTaWatt Energy monitor."""
from __future__ import annotations

import logging

import pyasic
from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
)
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


# TODO: This needs an update.  Lots of weird lint errors here.
class MinerPowerLimitNumber(CoordinatorEntity[MinerCoordinator], NumberEntity):
    """Defines a Miner Number to set the Power Limit of the Miner"""

    def __init__(
        self,
        coordinator: MinerCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['hostname']}-power_limit"

        self._attr_value = self.coordinator.data["miner_sensors"]["power_limit"]

        self._attr_min_value = 100
        self._attr_max_value = 5000
        self._attr_step = 100

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.data['hostname']} Power Limit"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return entity.DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.data["mac"])},
            manufacturer=self.coordinator.data["make"],
            model=self.coordinator.data["model"],
            name=f"{self.coordinator.data['make']} {self.coordinator.data['model']}",
        )

    async def async_set_value(self, value):
        """Update the current value."""

        miner = self.coordinator.miner
        if not miner.supports_autotuning:
            raise TypeError(f"{miner} does not support setting power limit.")

        result = await miner.set_power_limit(int(value))
        if not result:
            raise pyasic.APIError("Failed to set wattage.")

        self._attr_value = value
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:

        self._attr_value = self.coordinator.data["miner_sensors"]["power_limit"]

        super()._handle_coordinator_update()
