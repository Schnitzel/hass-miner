"""Config flow for Miner."""
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant import core
from homeassistant import exceptions
import pyasic

from .const import CONF_HOSTNAME
from .const import CONF_IP
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# async def _async_has_devices(hass: HomeAssistant) -> bool:
#     """Return if there are devices that can be discovered."""
#     # TODO Check if there are any devices that can be discovered in the network.
#     devices = await hass.async_add_executor_job(my_pypi_dependency.discover)
#     return len(devices) > 0


# config_entry_flow.register_discovery_flow(DOMAIN, "Miner", _async_has_devices)


async def validate_input(
    data: dict[str, str]
) -> dict[str, str]:
    """Validate the user input allows us to connect."""
    miner_ip = data.get(CONF_IP)

    try:
        miner = await pyasic.get_miner(miner_ip)
        if miner is None:
            return {"base": "cannot_connect"}
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Unexpected exception")
        return {"base": "unknown"}

    return {}


class MinerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Miner."""

    VERSION = 1

    def __init__(self):
        """Initialize."""
        self._data = {}

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            user_input = {}

        schema = vol.Schema(
            {
                vol.Required(CONF_IP, default=user_input.get(CONF_IP, "")): str,
            }
        )
        if not user_input:
            return self.async_show_form(step_id="user", data_schema=schema)

        if not (errors := await validate_input(user_input)):
            self._data.update(user_input)
            return await self.async_step_hostname()

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_hostname(self, user_input=None):
        """Ask for Hostname if we can't load it automated"""

        miner_ip = self._data.get(CONF_IP)
        miner = await pyasic.get_miner(miner_ip) # should be fast, cached
        hn = await miner.get_hostname() # TODO: this should be replaced with something, MAC maybe?  Hostname can be duplicates (mostly on stock).

        if user_input is None:
            user_input = {}

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOSTNAME,
                    default=user_input.get(CONF_HOSTNAME, hn),
                ): str,
            }
        )
        if not user_input:
            return self.async_show_form(step_id="hostname", data_schema=data_schema)

        data = {**self._data, **user_input}

        return self.async_create_entry(title=data[CONF_HOSTNAME], data=data)


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
