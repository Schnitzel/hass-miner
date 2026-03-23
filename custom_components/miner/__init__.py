"""The Miner integration."""
from __future__ import annotations

import sys

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_IP
from .const import DOMAIN
from .const import PYASIC_VERSION

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
]


def _ensure_pyasic():
    """Ensure pyasic is installed and imported (runs in executor)."""
    import importlib

    def try_import():
        try:
            from importlib.metadata import version
            import pyasic
            # Verify the module actually loaded correctly
            if not hasattr(pyasic, "get_miner"):
                raise ImportError("pyasic module incomplete")
            if version("pyasic") != PYASIC_VERSION:
                raise ImportError("Version mismatch")
            return pyasic
        except Exception:
            return None

    pyasic = try_import()
    if pyasic:
        return pyasic

    # Need to install/reinstall
    from .patch import install_package
    install_package(f"pyasic=={PYASIC_VERSION}", force_reinstall=True)

    # Clear any cached broken imports
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("pyasic"):
            del sys.modules[mod_name]

    import pyasic
    return pyasic


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
