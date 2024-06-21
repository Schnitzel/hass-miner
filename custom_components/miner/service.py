"""The Miner component services."""
from __future__ import annotations

import logging

import pyasic
from homeassistant.const import CONF_MAC, CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.core import ServiceCall

from .const import CONF_IP, CONF_RPC_PASSWORD, CONF_WEB_USERNAME, CONF_WEB_PASSWORD, CONF_SSH_USERNAME, \
    CONF_SSH_PASSWORD
from .const import DOMAIN
from .const import SERVICE_REBOOT
from .const import SERVICE_RESTART_BACKEND

LOGGER = logging.getLogger(__name__)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Service handler setup."""

    async def get_miner(call: ServiceCall):
        miners = hass.data[DOMAIN]
        miner_id = call.data[CONF_DEVICE_ID]

        if miner_id is None or miner_id not in miners:
            LOGGER.error(
                f"Cannot get miner, must specify a miner from [{miners}]",
            )
            return
        return miners[miner_id].miner

    async def reboot(call: ServiceCall) -> None:
        miner = await get_miner(call)
        if miner is not None:
            await miner.reboot()

    hass.services.async_register(DOMAIN, SERVICE_REBOOT, reboot)

    async def restart_backend(call: ServiceCall) -> None:
        miner = await get_miner(call)
        if miner is not None:
            await miner.restart_backend()

    hass.services.async_register(DOMAIN, SERVICE_RESTART_BACKEND, restart_backend)
