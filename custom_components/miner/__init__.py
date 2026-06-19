"""ASIC Miner integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_BOOT_TIMEOUT,
    CONF_POWER_ENTITY,
    CONF_SCAN_INTERVAL,
    DEFAULT_BOOT_TIMEOUT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import MinerCoordinator

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ASIC Miner from a config entry."""
    # Options override entry data (e.g. a VNish web password added after setup).
    password = entry.options.get(CONF_PASSWORD) or entry.data.get(CONF_PASSWORD)
    coordinator = MinerCoordinator(
        hass,
        ip=entry.data[CONF_HOST],
        entry_id=entry.entry_id,
        username=entry.data.get(CONF_USERNAME),
        password=password,
        scan_interval=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        power_entity=entry.options.get(CONF_POWER_ENTITY) or None,
        boot_timeout=entry.options.get(CONF_BOOT_TIMEOUT, DEFAULT_BOOT_TIMEOUT),
    )
    await coordinator.async_setup_power_tracking()
    entry.async_on_unload(coordinator._stop_power_tracking)

    # Offline resilience: load the cached device profile, then do a NON-raising
    # refresh. If the miner is reachable we get live data; if not, we may still
    # have a cached profile and can load entities (showing unavailable).
    await coordinator.async_load_profile()
    await coordinator.async_refresh()

    # Only bail (and let HA retry) when we truly know nothing about the miner:
    # the refresh failed AND we have no cached profile AND no data. A never-seen
    # miner that is offline at first setup still behaves as before.
    if (
        not coordinator.last_update_success
        and coordinator.profile is None
        and coordinator.data is None
    ):
        raise ConfigEntryNotReady(
            f"Miner at {entry.data[CONF_HOST]} is unreachable and no cached "
            "profile exists yet"
        )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change (e.g. category toggles, scan interval, password)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
