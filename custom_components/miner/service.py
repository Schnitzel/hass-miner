"""The Miner component services."""
from __future__ import annotations

import logging

import pyasic
from homeassistant.const import CONF_MAC
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
        mac = call.data.get(CONF_MAC)
        miners = hass.data[DOMAIN]

        if mac is None or mac not in miners:
            LOGGER.error(
                f"Cannot get miner, must specify a mac from [{miners}]",
            )
            return
        miner = await pyasic.get_miner(miners[mac].data[CONF_IP])

        entry = miners[mac]
        if miner.api is not None:
            if miner.api.pwd is not None:
                miner.api.pwd = entry.data.get(CONF_RPC_PASSWORD, "")

        if miner.web is not None:
            miner.web.username = entry.data.get(CONF_WEB_USERNAME, "")
            miner.web.pwd = entry.data.get(CONF_WEB_PASSWORD, "")

        if miner.ssh is not None:
            miner.ssh.username = entry.data.get(CONF_SSH_USERNAME, "")
            miner.ssh.pwd = entry.data.get(CONF_SSH_PASSWORD, "")
        return miner


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
