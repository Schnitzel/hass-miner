"""ASIC Miner integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import MinerCoordinator

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.NUMBER,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ASIC Miner from a config entry."""
    coordinator = MinerCoordinator(
        hass,
        ip=entry.data[CONF_HOST],
        entry_id=entry.entry_id,
        username=entry.data.get(CONF_USERNAME),
        password=entry.data.get(CONF_PASSWORD),
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
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
