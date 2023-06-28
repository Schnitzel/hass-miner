"""Support for IoTaWatt Energy monitor."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import POWER_WATT
from homeassistant.const import TEMP_CELSIUS
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
    "board_temperature": MinerSensorEntityDescription(
        "Board Temperature",
        native_unit_of_measurement=TEMP_CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    "chip_temperature": MinerSensorEntityDescription(
        "Chip Temperature",
        native_unit_of_measurement=TEMP_CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    "hashrate": MinerSensorEntityDescription(
        "Hashrate",
        native_unit_of_measurement="TH/s",
        state_class=SensorStateClass.MEASUREMENT,
        device_class="Hashrate",
    ),
    "ideal_hashrate": MinerSensorEntityDescription(
        "Hashrate",
        native_unit_of_measurement="TH/s",
        state_class=SensorStateClass.MEASUREMENT,
        device_class="Hashrate",
    ),
    "board_hashrate": MinerSensorEntityDescription(
        "Board Hashrate",
        native_unit_of_measurement="TH/s",
        state_class=SensorStateClass.MEASUREMENT,
        device_class="Hashrate",
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
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    sensor_created = set()

    @callback
    def _create_miner_entity(key: str) -> MinerSensor:
        """Create a miner sensor entity."""
        sensor_created.add(key)
        description = ENTITY_DESCRIPTION_KEY_MAP.get(
            key, MinerSensorEntityDescription("base_sensor")
        )
        return MinerSensor(
            coordinator=coordinator, key=key, entity_description=description
        )

    @callback
    def _create_board_entity(board: str, sensor: str) -> MinerBoardSensor:
        """Create a board sensor entity."""
        sensor_created.add(f"{board}-{sensor}")
        description = ENTITY_DESCRIPTION_KEY_MAP.get(
            sensor, MinerSensorEntityDescription("base_sensor")
        )
        return MinerBoardSensor(
            coordinator=coordinator,
            board=board,
            sensor=sensor,
            entity_description=description,
        )

    await coordinator.async_config_entry_first_refresh()
    sensors = []
    sensors.extend(
        _create_miner_entity(key) for key in coordinator.data["miner_sensors"]
    )
    if coordinator.data["board_sensors"]:
        for board in coordinator.data["board_sensors"]:
            sensors.extend(
                _create_board_entity(board, sensor)
                for sensor in coordinator.data["board_sensors"][board]
            )
    if sensors:
        async_add_entities(sensors)

    @callback
    def new_data_received():
        """Check for new sensors."""
        sensors = []
        sensors.extend(
            _create_miner_entity(key)
            for key in coordinator.data["miner_sensors"]
            if key not in sensor_created
        )

        if coordinator.data["board_sensors"]:
            for board in coordinator.data["board_sensors"]:
                sensors.extend(
                    _create_board_entity(board, sensor)
                    for sensor in coordinator.data["board_sensors"][board]
                    if f"{board}-{sensor}" not in sensor_created
                )

        if sensors:
            async_add_entities(sensors)

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
        self._attr_force_update = True

    @property
    def _sensor_data(self):
        """Return sensor data."""
        return self.coordinator.data["miner_sensors"][self._key]

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.data['hostname']} {self.entity_description.key}"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return entity.DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.data["mac"])},
            manufacturer=self.coordinator.data["make"],
            model=self.coordinator.data["model"],
            name=f"{self.coordinator.data['make']} {self.coordinator.data['model']}",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        super()._handle_coordinator_update()

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._sensor_data


class MinerBoardSensor(CoordinatorEntity[MinerCoordinator], SensorEntity):
    """Defines a Miner Sensor."""

    entity_description: MinerSensorEntityDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        board: str,
        sensor: str,
        entity_description: MinerSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['hostname']}-{board}-{sensor}"
        self._board = board
        self._sensor = sensor
        self.entity_description = entity_description
        self._attr_force_update = True

    @property
    def _sensor_data(self):
        """Return sensor data."""
        if (
            self._board in self.coordinator.data["board_sensors"]
            and self._sensor in self.coordinator.data["board_sensors"][self._board]
        ):
            return self.coordinator.data["board_sensors"][self._board][self._sensor]
        else:
            return None

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.data['hostname']} Board #{self._board} {self.entity_description.key}"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return entity.DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.data["mac"])},
            manufacturer=self.coordinator.data["make"],
            model=self.coordinator.data["model"],
            name=f"{self.coordinator.data['make']} {self.coordinator.data['model']}",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        super()._handle_coordinator_update()

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._sensor_data
