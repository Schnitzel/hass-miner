"""Support for IoTaWatt Energy monitor."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.switch import SwitchEntity
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
        self._attr_unique_id = f"{self.coordinator.data['mac']}-active"
        self._attr_is_on = self.coordinator.data["is_mining"]

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.entry.title} active"

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

    async def async_turn_on(self) -> None:
        """Turn on miner."""
        miner = self.coordinator.miner
        _LOGGER.debug("%s: Resume mining.", self.coordinator.entry.title)
        if not miner.supports_shutdown:
            raise TypeError(f"{miner} does not support shutdown mode.")
        self._attr_is_on = True
        await miner.resume_mining()
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn off miner."""
        miner = self.coordinator.miner
        _LOGGER.debug("%s: Stop mining.", self.coordinator.entry.title)
        if not miner.supports_shutdown:
            raise TypeError(f"{miner} does not support shutdown mode.")
        self._attr_is_on = False
        await miner.stop_mining()
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        is_mining = self.coordinator.data["is_mining"]
        if is_mining is not None:
            self._attr_is_on = self.coordinator.data["is_mining"]

        super()._handle_coordinator_update()
