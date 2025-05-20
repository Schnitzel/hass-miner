"""Support for Miner sensors."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import EntityCategory
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import REVOLUTIONS_PER_MINUTE
from homeassistant.const import UnitOfPower
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .const import JOULES_PER_TERA_HASH
from .const import TERA_HASH_PER_SECOND
from .coordinator import MinerCoordinator

_LOGGER = logging.getLogger(__name__)


ENTITY_DESCRIPTION_KEY_MAP: dict[str, SensorEntityDescription] = {
    "temperature": SensorEntityDescription(
        key="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_temperature": SensorEntityDescription(
        key="Board Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "chip_temperature": SensorEntityDescription(
        key="Chip Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "hashrate": SensorEntityDescription(
        key="Hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "ideal_hashrate": SensorEntityDescription(
        key="Ideal Hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "active_preset_name": SensorEntityDescription(
        key="Active Preset Name",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "board_hashrate": SensorEntityDescription(
        key="Board Hashrate",
        native_unit_of_measurement=TERA_HASH_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "power_limit": SensorEntityDescription(
        key="Power Limit",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "miner_consumption": SensorEntityDescription(
        key="Miner Consumption",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "efficiency": SensorEntityDescription(
        key="Efficiency",
        native_unit_of_measurement=JOULES_PER_TERA_HASH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "fan_speed": SensorEntityDescription(
        key="Fan Speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    def _create_miner_entity(sensor: str) -> MinerSensor:
        """Create a miner sensor entity."""
        description = ENTITY_DESCRIPTION_KEY_MAP.get(
            sensor, SensorEntityDescription(key="base_sensor")
        )
        return MinerSensor(
            coordinator=coordinator,
            sensor=sensor,
            entity_description=description,
        )

    def _create_board_entity(board_num: int, sensor: str) -> MinerBoardSensor:
        """Create a board sensor entity."""
        description = ENTITY_DESCRIPTION_KEY_MAP.get(
            sensor, SensorEntityDescription(key="base_sensor")
        )
        return MinerBoardSensor(
            coordinator=coordinator,
            board_num=board_num,
            sensor=sensor,
            entity_description=description,
        )

    def _create_fan_entity(fan_num: int, sensor: str) -> MinerFanSensor:
        """Create a fan sensor entity."""
        description = ENTITY_DESCRIPTION_KEY_MAP.get(
            sensor, SensorEntityDescription(key="base_sensor")
        )
        return MinerFanSensor(
            coordinator=coordinator,
            fan_num=fan_num,
            sensor=sensor,
            entity_description=description,
        )

    await coordinator.async_config_entry_first_refresh()

    sensors = []
    for s in coordinator.data["miner_sensors"]:
        sensors.append(_create_miner_entity(s))
    for board in range(coordinator.miner.expected_hashboards):
        for s in ["board_temperature", "chip_temperature", "board_hashrate"]:
            sensors.append(_create_board_entity(board, s))
    for fan in range(coordinator.miner.expected_fans):
        for s in ["fan_speed"]:
            sensors.append(_create_fan_entity(fan, s))
    async_add_entities(sensors)


class MinerSensor(CoordinatorEntity[MinerCoordinator], SensorEntity):
    """Defines a Miner Sensor."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        sensor: str,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['mac']}-{sensor}"
        self._sensor = sensor
        self.entity_description = entity_description

    @property
    def _sensor_data(self):
        """Return sensor data."""
        try:
            return self.coordinator.data["miner_sensors"][self._sensor]
        except LookupError:
            return None

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} {self.entity_description.key}"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return entity.DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.data["mac"])},
            manufacturer=self.coordinator.data["make"],
            model=self.coordinator.data["model"],
            sw_version=self.coordinator.data["fw_ver"],
            name=f"{self.coordinator.config_entry.title}",
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._sensor_data

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available


class MinerBoardSensor(CoordinatorEntity[MinerCoordinator], SensorEntity):
    """Defines a Miner Board Sensor."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        board_num: int,
        sensor: str,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['mac']}-{board_num}-{sensor}"
        self._board_num = board_num
        self._sensor = sensor
        self.entity_description = entity_description

    @property
    def _sensor_data(self):
        """Return sensor data."""
        try:
            return self.coordinator.data["board_sensors"][self._board_num][self._sensor]
        except LookupError:
            return None

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} Board #{self._board_num} {self.entity_description.key}"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return entity.DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.data["mac"])},
            manufacturer=self.coordinator.data["make"],
            model=self.coordinator.data["model"],
            sw_version=self.coordinator.data["fw_ver"],
            name=f"{self.coordinator.config_entry.title}",
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._sensor_data

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available


class MinerFanSensor(CoordinatorEntity[MinerCoordinator], SensorEntity):
    """Defines a Miner Fan Sensor."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        fan_num: int,
        sensor: str,
        entity_description: SensorEntityDescription,
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
        try:
            return self.coordinator.data["fan_sensors"][self._fan_num][self._sensor]
        except LookupError:
            return None

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} Fan #{self._fan_num} {self.entity_description.key}"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return entity.DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.data["mac"])},
            manufacturer=self.coordinator.data["make"],
            model=self.coordinator.data["model"],
            sw_version=self.coordinator.data["fw_ver"],
            name=f"{self.coordinator.config_entry.title}",
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._sensor_data

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available
