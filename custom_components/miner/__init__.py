"""ASIC Miner integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import MinerCoordinator
from .discovery import async_discover_miners

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.NUMBER,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up automatic network discovery."""
    hass.async_create_background_task(
        async_discover_miners(hass),
        "Discover ASIC miners",
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ASIC Miner from a config entry."""
    coordinator = MinerCoordinator(
        hass,
        ip=entry.data[CONF_HOST],
        entry_id=entry.entry_id,
        username=entry.data.get(CONF_USERNAME),
        password=entry.data.get(CONF_PASSWORD),
        scan_interval=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    # Offline resilience: load any cached device profile first, then attempt a
    # refresh. Unlike async_config_entry_first_refresh(), a failed refresh does
    # not abort setup as long as we have *something* to build entities from
    # (live data or a cached profile) — the entry loads with entities showing
    # ``unavailable`` and re-populates once the miner answers. Only raise
    # ConfigEntryNotReady when we have neither a successful poll nor a cache.
    await coordinator.async_load_profile()
    await coordinator.async_refresh()
    if (
        not coordinator.last_update_success
        and coordinator.profile is None
        and coordinator.data is None
    ):
        raise ConfigEntryNotReady(
            f"Could not reach miner at {entry.data[CONF_HOST]} and no cached "
            "device profile is available yet"
        )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
