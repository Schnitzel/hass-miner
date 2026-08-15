"""The Miner integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceEntry

from .const import CONF_IP
from .const import CONF_MAC
from .const import DOMAIN
from .const import PYASIC_VERSION
from .patch import ensure_pyasic

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    # Platform.SELECT,  # TODO: select.py needs proper implementation
]


def _ensure_pyasic():
    """Ensure pyasic is installed and imported (runs in executor)."""
    return ensure_pyasic(PYASIC_VERSION)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Miner from a config entry."""
    # Import pyasic in executor to avoid blocking the event loop
    pyasic = await hass.async_add_executor_job(_ensure_pyasic)

    # Import coordinator and services AFTER pyasic is installed
    from .coordinator import MinerCoordinator
    from .services import async_setup_services

    miner_ip = config_entry.data[CONF_IP]
    miner = await pyasic.get_miner(miner_ip)

    if miner is None:
        raise ConfigEntryNotReady("Miner could not be found.")

    m_coordinator = MinerCoordinator(hass, config_entry)
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = m_coordinator

    await m_coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    await async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Allow deleting stale devices from the UI (#593 leftovers).

    Only the device whose identifier is exactly the MAC pinned in the config
    entry is live; anything else attached to this entry (a device keyed on a
    lowercase or missing MAC from an earlier version) can be removed. The
    comparison is deliberately case-sensitive: the stale duplicate typically
    differs from the live device only by MAC letter case.
    """
    mac = config_entry.data.get(CONF_MAC)
    return not any(
        domain == DOMAIN and mac is not None and str(ident) == mac
        for domain, ident in device_entry.identifiers
    )
