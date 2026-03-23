"""Support for Miner shutdown."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
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
    if coordinator.miner.supports_shutdown:
        async_add_entities(
            [
                MinerActiveSwitch(
                    coordinator=coordinator,
                )
            ]
        )


class MinerActiveSwitch(CoordinatorEntity[MinerCoordinator], SwitchEntity):
    """Defines a Miner Switch to pause and unpause the miner.

    For miners with power modes (e.g. Antminer S19K Pro with Sleep/Normal/HEM),
    this switch uses explicit mode configuration instead of resume_mining(),
    because resume_mining() does not reliably bring multi-mode miners out of sleep.

    The S19K Pro has three states: Sleep, Normal, and High Energy Mode (HEM).
    A binary on/off toggle maps to: OFF = Sleep mode, ON = previous mode (or Normal).
    """

    def __init__(
        self,
        coordinator: MinerCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['mac']}-active"
        self._attr_is_on = self.coordinator.data["is_mining"]
        self.updating_switch = False
        self._last_mining_mode = None

        # Try to capture current mining mode at init if miner is active
        if self._attr_is_on:
            try:
                config_data = self.coordinator.data.get("config")
                if config_data and hasattr(config_data, "mining_mode"):
                    self._last_mining_mode = config_data.mining_mode
                    _LOGGER.debug(
                        "%s: Captured initial mining mode: %s",
                        self.coordinator.config_entry.title,
                        self._last_mining_mode,
                    )
            except (AttributeError, TypeError):
                pass

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} active"

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

    async def async_turn_on(self) -> None:
        """Turn on miner.

        For miners with power modes (e.g. Antminer S19K Pro), we use
        send_config() with the previously stored mining mode to bring the miner
        out of sleep. This is necessary because resume_mining() alone does not
        work for miners with 3 states (Sleep/Normal/HEM).

        For miners without power modes (e.g. Bitaxe), resume_mining() is used.
        """
        miner = self.coordinator.miner
        _LOGGER.debug("%s: Resume mining.", self.coordinator.config_entry.title)
        if not miner.supports_shutdown:
            raise TypeError(f"{miner}: Shutdown not supported.")

        self._attr_is_on = True

        if miner.supports_power_modes:
            # S19K Pro and similar: use explicit mode setting to wake from sleep.
            # resume_mining() does NOT work for these miners - it leaves them in
            # sleep mode. We must set the mining_mode via send_config().
            mode_set = False
            try:
                config = await miner.get_config()
                if self._last_mining_mode is not None:
                    config.mining_mode = self._last_mining_mode
                    _LOGGER.info(
                        "%s: Restoring previous mining mode: %s",
                        self.coordinator.config_entry.title,
                        self._last_mining_mode,
                    )
                else:
                    # Default to normal mode if no previous mode stored
                    # (e.g. after HA restart while miner was sleeping)
                    from pyasic.config.mining import MiningModeNormal
                    config.mining_mode = MiningModeNormal()
                    _LOGGER.info(
                        "%s: No previous mining mode stored, defaulting to Normal.",
                        self.coordinator.config_entry.title,
                    )
                await miner.send_config(config)
                mode_set = True
                _LOGGER.debug(
                    "%s: send_config() succeeded for wake-up.",
                    self.coordinator.config_entry.title,
                )
            except Exception as err:
                _LOGGER.warning(
                    "%s: Failed to set mining mode via send_config(): %s. "
                    "Falling back to resume_mining().",
                    self.coordinator.config_entry.title,
                    err,
                )

            if not mode_set:
                # Fallback: try resume_mining() even though it usually doesn't
                # work for multi-mode miners. Some firmware versions may support it.
                try:
                    await miner.resume_mining()
                    _LOGGER.debug(
                        "%s: resume_mining() fallback executed.",
                        self.coordinator.config_entry.title,
                    )
                except Exception as resume_err:
                    _LOGGER.error(
                        "%s: resume_mining() fallback also failed: %s",
                        self.coordinator.config_entry.title,
                        resume_err,
                    )
        else:
            # Bitaxe and simple miners: resume_mining() works fine
            try:
                await miner.resume_mining()
            except Exception as err:
                _LOGGER.warning(
                    "%s: Resume API returned error (may still work): %s",
                    self.coordinator.config_entry.title,
                    err,
                )

        self.updating_switch = True
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn off miner.

        For miners with power modes, we save the current mining mode before
        stopping so it can be restored on turn_on.
        """
        miner = self.coordinator.miner
        _LOGGER.debug("%s: Stop mining.", self.coordinator.config_entry.title)
        if not miner.supports_shutdown:
            raise TypeError(f"{miner}: Shutdown not supported.")

        # Save current mining mode before stopping (for multi-mode miners)
        if miner.supports_power_modes:
            try:
                config_data = self.coordinator.data.get("config")
                if config_data and hasattr(config_data, "mining_mode"):
                    self._last_mining_mode = config_data.mining_mode
                    _LOGGER.debug(
                        "%s: Saved mining mode from coordinator: %s",
                        self.coordinator.config_entry.title,
                        self._last_mining_mode,
                    )
                else:
                    # Try to fetch current config directly from miner
                    config = await miner.get_config()
                    self._last_mining_mode = config.mining_mode
                    _LOGGER.debug(
                        "%s: Fetched and saved mining mode: %s",
                        self.coordinator.config_entry.title,
                        self._last_mining_mode,
                    )
            except Exception as err:
                _LOGGER.warning(
                    "%s: Could not save mining mode: %s",
                    self.coordinator.config_entry.title,
                    err,
                )
                # Keep previous _last_mining_mode if we had one; only clear if
                # we never had a mode stored at all
                if self._last_mining_mode is None:
                    _LOGGER.warning(
                        "%s: No mining mode stored. On next turn_on, Normal mode "
                        "will be used as default.",
                        self.coordinator.config_entry.title,
                    )

        self._attr_is_on = False

        try:
            await miner.stop_mining()
        except Exception as err:
            _LOGGER.warning(
                "%s: Stop API returned error (may still work): %s",
                self.coordinator.config_entry.title,
                err,
            )

        self.updating_switch = True
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        is_mining = self.coordinator.data["is_mining"]
        if is_mining is not None:
            if self.updating_switch:
                if is_mining == self._attr_is_on:
                    self.updating_switch = False
            if not self.updating_switch:
                self._attr_is_on = is_mining

        # Keep _last_mining_mode up to date while miner is active.
        # This ensures we always have a valid mode to restore after HA restarts.
        if is_mining:
            try:
                config_data = self.coordinator.data.get("config")
                if config_data and hasattr(config_data, "mining_mode"):
                    mode = config_data.mining_mode
                    if mode is not None:
                        self._last_mining_mode = mode
            except (AttributeError, TypeError):
                pass

        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available
