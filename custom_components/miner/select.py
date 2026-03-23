"""A selector for the miner's mining mode."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyasic

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
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
    if (
        coordinator.miner.supports_power_modes
        and not coordinator.miner.supports_autotuning
    ):
        async_add_entities(
            [
                MinerPowerModeSwitch(
                    coordinator=coordinator,
                )
            ]
        )


class MinerPowerModeSwitch(CoordinatorEntity[MinerCoordinator], SelectEntity):
    """A selector for the miner's mining mode."""

    def __init__(
        self,
        coordinator: MinerCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['mac']}-power-mode"

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} power mode"

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
    def current_option(self) -> str | None:
        """The current option selected with the select."""
        _mode_map = {
            "normal": "Normal",
            "sleep": "Sleep",
            "low": "Low",
            "high": "Normal",  # pyasic HPM incorrectly maps to miner-mode 0
        }
        try:
            config = self.coordinator.data.get("config")
            if config and hasattr(config, "mining_mode"):
                mode_str = str(getattr(config.mining_mode, "mode", "")).lower()
                return _mode_map.get(mode_str)
        except (AttributeError, TypeError):
            pass
        return None

    @property
    def options(self) -> list[str]:
        """The allowed options for the selector.

        S19K Pro firmware FR-1.17 modes:
          Normal = miner-mode 0
          Sleep  = miner-mode 1
          HEM    = miner-mode 2  (High Energy Mode)
        """
        return ["Normal", "Sleep", "HEM"]

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        from pyasic.config.mining import MiningModeNormal, MiningModeSleep

        # MiningModeHEM: pyasic has no native class for HEM (mode 2).
        # Antminer firmware mode values (bitmain-work-mode on GET, miner-mode on POST):
        #   0 = Normal, 1 = Sleep, 2 = HEM (High Energy Mode), 3 = LPM
        # pyasic's as_am_modern() consistently uses the "miner-mode" key for POSTs,
        # so we do the same here. MinerConfig.as_am_modern() spreads this directly
        # into the POST body sent to set_miner_conf.cgi.
        class MiningModeHEM(MiningModeNormal):
            """Antminer High Energy Mode (miner-mode: 2) for S19K Pro."""

            def as_am_modern(self) -> dict:
                return {"miner-mode": 2}

        option_map = {
            "Normal": MiningModeNormal,
            "Sleep": MiningModeSleep,
            "HEM": MiningModeHEM,
        }
        _LOGGER.debug(
            "%s: Setting mining mode to %s.",
            self.coordinator.config_entry.title,
            option,
        )
        cfg = await self.coordinator.miner.get_config()
        cfg.mining_mode = option_map[option]()
        await self.coordinator.miner.send_config(cfg)
