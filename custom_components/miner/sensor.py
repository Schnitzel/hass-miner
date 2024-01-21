"""Support for IoTaWatt Energy monitor."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfTemperature, REVOLUTIONS_PER_MINUTE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEVICE_CLASS_EFFICIENCY,
    DEVICE_CLASS_HASHRATE,
    DOMAIN,
    JOULES_PER_TERA_HASH,
    TERA_HASH_PER_SECOND,
)
from .coordinator import MinerCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class MinerSensorEntityDescription(SensorEntityDescription):
    """Class describing ASIC Miner sensor entities."""

    value: Callable = None


class MinerNumberEntityDescription(SensorEntityDescription):
    """Class describing ASIC Miner number entities."""

    value: Callable = None


ENTITY_DESCRIPTION_KEY_MAP: dict[
    str, MinerSensorEntityDescription or MinerNumberEntityDescription
] = {
    "temperature": MinerSensorEntityDescription(
        "Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "board_temperature": MinerSensorEntityDescription(
        "Board Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "chip_temperature": MinerSensorEntityDescription(
        "Chip Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "hashrate": MinerSensorEntityDescription(
        "Hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "ideal_hashrate": MinerSensorEntityDescription(
        "Ideal Hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "board_hashrate": MinerSensorEntityDescription(
        "Board Hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "power_limit": MinerSensorEntityDescription(
        "Power Limit",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
    ),
    "miner_consumption": MinerSensorEntityDescription(
        "Miner Consumption",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
    ),
    "efficiency": MinerSensorEntityDescription(
        "Efficiency",
        native_unit_of_measurement=JOULES_PER_TERA_HASH,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "fan_speed": MinerSensorEntityDescription(
        "Fan Speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
    )
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
    def _create_board_entity(board_num: int, sensor: str) -> MinerBoardSensor:
        """Create a board sensor entity."""
        sensor_created.add(f"board_{board_num}-{sensor}")
        description = ENTITY_DESCRIPTION_KEY_MAP.get(
            sensor, MinerSensorEntityDescription("base_sensor")
        )
        return MinerBoardSensor(
            coordinator=coordinator,
            board_num=board_num,
            sensor=sensor,
            entity_description=description,
        )

    @callback
    def _create_fan_entity(fan_num: int, sensor: str) -> MinerFanSensor:
        """Create a fan sensor entity."""
        sensor_created.add(f"fan_{fan_num}-{sensor}")
        description = ENTITY_DESCRIPTION_KEY_MAP.get(
            sensor, MinerSensorEntityDescription("base_sensor")
        )
        return MinerFanSensor(
            coordinator=coordinator,
            fan_num=fan_num,
            sensor=sensor,
            entity_description=description,
        )

    await coordinator.async_config_entry_first_refresh()

    sensors = []
    sensors.extend(
        _create_miner_entity(key) for key in coordinator.data["miner_sensors"]
    )
    for board in range(coordinator.miner.expected_hashboards):
        sensors.extend(
            _create_board_entity(board, sensor)
            for sensor in ["board_temperature", "chip_temperature", "board_hashrate"]
        )
    for fan in range(coordinator.miner.fan_count):
        sensors.extend(
            _create_fan_entity(fan, sensor)
            for sensor in ["fan_speed"]
        )
    if sensors:
        async_add_entities(sensors)


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
        self._attr_unique_id = f"{self.coordinator.data['mac']}-{key}"
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
        return f"{self.coordinator.entry.title} {self.entity_description.key}"

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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        super()._handle_coordinator_update()

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._sensor_data


class MinerBoardSensor(CoordinatorEntity[MinerCoordinator], SensorEntity):
    """Defines a Miner Board Sensor."""

    entity_description: MinerSensorEntityDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        board_num: int,
        sensor: str,
        entity_description: MinerSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['mac']}-{board_num}-{sensor}"
        self._board_num = board_num
        self._sensor = sensor
        self.entity_description = entity_description
        self._attr_force_update = True

    @property
    def _sensor_data(self):
        """Return sensor data."""
        if (
            self._board_num in self.coordinator.data["board_sensors"]
            and self._sensor in self.coordinator.data["board_sensors"][self._board_num]
        ):
            return self.coordinator.data["board_sensors"][self._board_num][self._sensor]
        else:
            return None

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.entry.title} Board #{self._board_num} {self.entity_description.key}"

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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        super()._handle_coordinator_update()

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._sensor_data


class MinerFanSensor(CoordinatorEntity[MinerCoordinator], SensorEntity):
    """Defines a Miner Fan Sensor."""

    entity_description: MinerSensorEntityDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        fan_num: int,
        sensor: str,
        entity_description: MinerSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['mac']}-{fan_num}-{sensor}"
        self._fan_num = fan_num
        self._sensor = sensor
        self.entity_description = entity_description
        self._attr_force_update = True

    @property
    def _sensor_data(self):
        """Return sensor data."""
        if (
            self._fan_num in self.coordinator.data["fan_sensors"]
            and self._sensor in self.coordinator.data["fan_sensors"][self._fan_num]
        ):
            return self.coordinator.data["fan_sensors"][self._fan_num][self._sensor]
        else:
            return None

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.entry.title} Fan #{self._fan_num} {self.entity_description.key}"

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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        super()._handle_coordinator_update()

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._sensor_data
