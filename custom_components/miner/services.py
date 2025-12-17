"""The Miner component services."""
from __future__ import annotations

import asyncio
import logging
from importlib.metadata import version

from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.core import ServiceCall
from homeassistant.helpers.device_registry import (
    async_get as async_get_device_registry,
)

from .const import DOMAIN
from .const import PYASIC_VERSION
from .const import SERVICE_REBOOT
from .const import SERVICE_RESTART_BACKEND
from .const import SERVICE_SET_WORK_MODE

# Ensure the expected pyasic version is available, importing MiningModeConfig
try:
    if version("pyasic") != PYASIC_VERSION:
        raise ImportError
    from pyasic.config.mining import MiningModeConfig  # type: ignore
except Exception:  # pragma: no cover - handled by dynamic install
    from .patch import install_package

    install_package(f"pyasic=={PYASIC_VERSION}")
    from pyasic.config.mining import MiningModeConfig  # type: ignore

LOGGER = logging.getLogger(__name__)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Service handler setup."""

    async def get_miners(call: ServiceCall):
        hass_devices = hass.data[DOMAIN]

        miner_ids = call.data[CONF_DEVICE_ID]

        if not miner_ids:
            return

        registry = async_get_device_registry(hass)

        return await asyncio.gather(
            *(
                [
                    hass_devices[registry.async_get(d).primary_config_entry].get_miner()
                    for d in miner_ids
                ]
            )
        )

    async def reboot(call: ServiceCall) -> None:
        miners = await get_miners(call)
        if len(miners) > 0:
            await asyncio.gather(*[miner.reboot() for miner in miners])

    hass.services.async_register(DOMAIN, SERVICE_REBOOT, reboot)

    async def restart_backend(call: ServiceCall) -> None:
        miners = await get_miners(call)
        if len(miners) > 0:
            await asyncio.gather(*[miner.restart_backend() for miner in miners])

    hass.services.async_register(DOMAIN, SERVICE_RESTART_BACKEND, restart_backend)

    async def set_work_mode(call: ServiceCall) -> None:
        miners = await get_miners(call)
        if len(miners) > 0:
            mode = call.data["mode"]

            async def set_mining_mode(miner):
                cfg_mode = MiningModeConfig.default()
                if mode == "high":
                    cfg_mode = MiningModeConfig.high()
                elif mode == "normal":
                    cfg_mode = MiningModeConfig.normal()
                elif mode == "low":
                    cfg_mode = MiningModeConfig.low()
                cfg = await miner.get_config()
                cfg.mining_mode = cfg_mode
                await miner.send_config(cfg)

            await asyncio.gather(*(set_mining_mode(miner) for miner in miners))

    hass.services.async_register(DOMAIN, SERVICE_SET_WORK_MODE, set_work_mode)
