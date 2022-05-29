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
from homeassistant.components.switch import (
    SwitchEntity,
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


@dataclass
class MinerSensorEntityDescription(SensorEntityDescription):
    """Class describing IotaWatt sensor entities."""

    value: Callable | None = None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    created = set()

    @callback
    def _create_entity(key: str) -> SwitchEntity:
        """Create a sensor entity."""
        created.add(key)

    await coordinator.async_config_entry_first_refresh()
    async_add_entities(
        [
            MinerActiveSwitch(
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


class MinerActiveSwitch(CoordinatorEntity[MinerCoordinator], SwitchEntity):
    """Defines a Miner Switch to pause and unpause the miner."""

    def __init__(
        self,
        coordinator: MinerCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['hostname']}-active"
        self._attr_is_on = self.coordinator.data["miner_sensors"]["temperature"] != 0

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.data['hostname']} active"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return entity.DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.data["hostname"])},
            manufacturer="Antminer",
            model=self.coordinator.data["model"],
            name=f"Antminer {self.coordinator.data['model']}",
        )

    async def async_turn_on(self) -> None:
        """Turn on miner."""
        self._attr_is_on = True
        await self.coordinator.miner.api.resume()
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn off miner."""
        self._attr_is_on = False
        await self.coordinator.miner.api.pause()
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:

        # There isn't really a good way to check if the Miner is on.
        # But when it's off there is no temperature reported, so we use this
        self._attr_is_on = self.coordinator.data["miner_sensors"]["temperature"] != 0

        super()._handle_coordinator_update()
