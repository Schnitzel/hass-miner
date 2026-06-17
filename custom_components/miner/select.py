"""Select platform for ASIC Miner integration.

BETA SOLUTION: VNish autotune-preset control. asic-rs is read-only for VNish
presets, so this entity drives the VNish REST API directly (see vnish.py).
Replace with the native miner method once asic-rs supports VNish writes.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import vnish
from .const import DOMAIN
from .coordinator import MinerCoordinator
from .entity import MinerEntity


class VnishPresetSelect(MinerEntity, SelectEntity):
    """[BETA] Select a VNish autotune preset by name."""

    _attr_name = "VNish Preset"
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator: MinerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_unique_id}_vnish_preset"

    @property
    def options(self) -> list[str]:
        return self.coordinator.vnish_presets or list(vnish.FALLBACK_PRESETS)

    @property
    def current_option(self) -> str | None:
        return self.coordinator.vnish_preset

    async def async_select_option(self, option: str) -> None:
        session = async_get_clientsession(self.hass)
        ok, msg = await vnish.apply_preset(
            session, self.coordinator.ip, self.coordinator.password, option
        )
        if ok:
            self.coordinator.vnish_preset = option
            self.async_write_ha_state()
        else:
            raise RuntimeError(f"VNish preset '{option}' failed: {msg}")
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MinerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[MinerEntity] = []

    if coordinator.is_vnish:
        entities.append(VnishPresetSelect(coordinator))

    async_add_entities(entities)
