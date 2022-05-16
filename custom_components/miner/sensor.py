"""Support for IoTaWatt Energy monitor."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
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
from homeassistant.const import TEMP_CELSIUS, POWER_WATT
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


@dataclass
class MinerSensorEntityDescription(SensorEntityDescription):
    """Class describing IotaWatt sensor entities."""

    value: Callable | None = None


class MinerNumberEntityDescription(SensorEntityDescription):
    """Class describing IotaWatt number entities."""

    value: Callable | None = None


ENTITY_DESCRIPTION_KEY_MAP: dict[
    str, MinerSensorEntityDescription or MinerNumberEntityDescription
] = {
    "temperature": MinerSensorEntityDescription(
        "Temperature",
        native_unit_of_measurement=TEMP_CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    "hashrate": MinerSensorEntityDescription(
        "Hashrate",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "power_limit": MinerSensorEntityDescription(
        "Power Limit",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
    ),
    "miner_consumption": MinerSensorEntityDescription(
        "Miner Consumption",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
    ),
    "scaled_power_limit": MinerSensorEntityDescription(
        "Scaled Power Limit",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    created = set()

    @callback
    def _create_entity(key: str) -> MinerSensor:
        """Create a sensor entity."""
        created.add(key)
        description = ENTITY_DESCRIPTION_KEY_MAP.get(
            key, MinerSensorEntityDescription("base_sensor")
        )
        return MinerSensor(
            coordinator=coordinator, key=key, entity_description=description
        )

    await coordinator.async_config_entry_first_refresh()
    async_add_entities(_create_entity(key) for key in coordinator.data["sensors"])

    @callback
    def new_data_received():
        """Check for new sensors."""
        entities = [
            _create_entity(key)
            for key in coordinator.data["sensors"]
            if key not in created
        ]
        if entities:
            async_add_entities(entities)

    coordinator.async_add_listener(new_data_received)


class MinerSensor(CoordinatorEntity[MinerCoordinator], SensorEntity):
    """Defines a Miner Sensor."""

    entity_description: MinerSensorEntityDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        key: str,
        entity_description: MinerSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['hostname']}-{key}"
        self._key = key
        self.entity_description = entity_description

    @property
    def _sensor_data(self):
        """Return sensor data."""
        return self.coordinator.data["sensors"][self._key]

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.data['hostname']} {self.entity_description.key}"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return entity.DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.data["hostname"])},
            manufacturer="Antminer",
            model=self.coordinator.data["model"],
            name=f"Antminer {self.coordinator.data['model']}",
            # sw_version=self.coordinator.data["version"],
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # if self._key not in self.coordinator.data:
        #     if self._attr_unique_id:
        #         entity_registry.async_get(self.hass).async_remove(self.entity_id)
        #     else:
        #         self.hass.async_create_task(self.async_remove())
        #     return

        super()._handle_coordinator_update()

    # @property
    # def extra_state_attributes(self) -> dict[str, str]:
    #     """Return the extra state attributes of the entity."""
    #     data = self._sensor_data
    #     attrs = {"type": data.getType()}
    #     if attrs["type"] == "Input":
    #         attrs["channel"] = data.getChannel()

    #     return attrs

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._sensor_data


# class MinerNumber(CoordinatorEntity[MinerCoordinator], NumberEntity):
#     """Defines a Miner Sensor."""

#     entity_description: MinerNumberEntityDescription

#     def __init__(
#         self,
#         coordinator: MinerCoordinator,
#         key: str,
#         entity_description: MinerNumberEntityDescription,
#     ) -> None:
#         """Initialize the sensor."""
#         super().__init__(coordinator=coordinator)

#         self._key = key
#         self.entity_description = entity_description

#     @property
#     def _sensor_data(self) -> Sensor:
#         """Return sensor data."""
#         return self.coordinator.data["sensors"][self._key]

#     @property
#     def name(self) -> str | None:
#         """Return name of the entity."""
#         return self._key

#     @property
#     def device_info(self) -> entity.DeviceInfo:
#         """Return device info."""
#         return entity.DeviceInfo(
#             manufacturer="Antminer",
#             model="S9",
#         )

#     @callback
#     def _handle_coordinator_update(self) -> None:
#         """Handle updated data from the coordinator."""
#         if self._key not in self.coordinator.data:
#             if self._attr_unique_id:
#                 entity_registry.async_get(self.hass).async_remove(self.entity_id)
#             else:
#                 self.hass.async_create_task(self.async_remove())
#             return

#         super()._handle_coordinator_update()

#     # @property
#     # def extra_state_attributes(self) -> dict[str, str]:
#     #     """Return the extra state attributes of the entity."""
#     #     data = self._sensor_data
#     #     attrs = {"type": data.getType()}
#     #     if attrs["type"] == "Input":
#     #         attrs["channel"] = data.getChannel()

#     #     return attrs

#     @property
#     def native_value(self) -> StateType:
#         """Return the state of the sensor."""
#         return self._sensor_data
