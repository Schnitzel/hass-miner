"""Button platform for ASIC Miner integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MinerCoordinator
from .entity import MinerEntity


class RestartButton(MinerEntity, ButtonEntity):
    """Restart the miner."""

    _attr_name = "Restart"
    _attr_icon = "mdi:restart"

    def __init__(self, coordinator: MinerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_unique_id}_restart"

    async def async_press(self) -> None:
        await self.coordinator.miner.restart()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MinerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[MinerEntity] = []

    # Gated on a miner capability flag. When the miner is None (offline at
    # startup) we cannot know it, so we skip the native entity; it appears after
    # the first successful connection + a reload.
    if coordinator.miner is not None and coordinator.miner.supports_restart:
        entities.append(RestartButton(coordinator))

    async_add_entities(entities)
