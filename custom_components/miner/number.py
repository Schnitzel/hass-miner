"""Support for IoTaWatt Energy monitor."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
import yaml
from unittest import case

from homeassistant.components import switch

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.number import (
    NumberEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity, entity_registry
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt

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
    def _create_entity(key: str) -> NumberEntity:
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


class MinerPowerLimitNumber(CoordinatorEntity[MinerCoordinator], NumberEntity):
    """Defines a Miner Number to set the Power Limit of the Miner"""

    def __init__(
        self,
        coordinator: MinerCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['hostname']}-power_limit"

        self._attr_value = self.coordinator.data["number"]["power_limit"]

        self._attr_min_value = 100
        self._attr_max_value = 5000
        self._attr_step = 100

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.data['hostname']} PowerLimit"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return entity.DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.data["hostname"])},
            manufacturer="Antminer",
            model=self.coordinator.data["model"],
            name=f"Antminer {self.coordinator.data['model']}",
        )

    async def async_set_value(self, value):
        """Update the current value."""

        miner = self.coordinator.miner
        await miner.get_config()
        updated_config = yaml.load(miner.config, Loader=yaml.SafeLoader)
        updated_config["autotuning"]["wattage"] = int(value)
        config_yaml = yaml.dump(updated_config, sort_keys=False)
        await miner.send_config(config_yaml)

        self._attr_value = value
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:

        self._attr_value = self.coordinator.data["number"]["power_limit"]

        super()._handle_coordinator_update()
