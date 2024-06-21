"""The Miner component services."""
from __future__ import annotations

import logging

import pyasic
from homeassistant.core import HomeAssistant
from homeassistant.core import ServiceCall

from .const import CONF_IP
from .const import DOMAIN
from .const import SERVICE_REBOOT
from .const import SERVICE_RESTART_BACKEND

LOGGER = logging.getLogger(__name__)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Service handler setup."""

    async def reboot(call: ServiceCall) -> None:
        ip = call.data.get(CONF_IP)

        miner = await pyasic.get_miner(ip)
        await miner.reboot()

    hass.services.async_register(DOMAIN, SERVICE_REBOOT, reboot)

    async def restart_backend(call: ServiceCall) -> None:
        ip = call.data.get(CONF_IP)

        miner = await pyasic.get_miner(ip)
        await miner.restart_backend()

    hass.services.async_register(DOMAIN, SERVICE_RESTART_BACKEND, restart_backend)
