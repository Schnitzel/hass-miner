"""Config flow for Miner."""
from homeassistant.helpers import config_entry_flow
from homeassistant import config_entries, core, exceptions
from .const import DOMAIN, CONF_IP, CONF_HOSTNAME

from API import APIError

import ipaddress

import voluptuous as vol

from miners.miner_factory import MinerFactory
import logging

_LOGGER = logging.getLogger(__name__)

# async def _async_has_devices(hass: HomeAssistant) -> bool:
#     """Return if there are devices that can be discovered."""
#     # TODO Check if there are any devices that can be discovered in the network.
#     devices = await hass.async_add_executor_job(my_pypi_dependency.discover)
#     return len(devices) > 0


# config_entry_flow.register_discovery_flow(DOMAIN, "Miner", _async_has_devices)


async def validate_input(
    hass: core.HomeAssistant, data: dict[str, str]
) -> dict[str, str]:
    """Validate the user input allows us to connect."""

    miner_ip = ipaddress.ip_address(data.get(CONF_IP))
    miner_factory = MinerFactory()
    miner_data = {}
    try:
        miner = await miner_factory.get_miner(miner_ip)
        miner_data = await miner.get_data()
    except APIError:
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

        if not (errors := await validate_input(self.hass, user_input)):
            self._data.update(user_input)
            return await self.async_step_hostname()

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_hostname(self, user_input=None):
        """Ask for Hostname if we can't load it automated"""

        miner_ip = ipaddress.ip_address(self._data.get(CONF_IP))
        miner_factory = MinerFactory()
        miner = await miner_factory.get_miner(miner_ip)
        miner_data = await miner.get_data()

        if user_input is None:
            user_input = {}

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOSTNAME,
                    default=user_input.get(CONF_HOSTNAME, miner_data["Hostname"]),
                ): str,
            }
        )
        if not user_input:
            return self.async_show_form(step_id="hostname", data_schema=data_schema)

        data = {**self._data, **user_input}

        # if errors := await validate_input(self.hass, data):
        #     return self.async_show_form(
        #         step_id="hostname", data_schema=data_schema, errors=errors
        #     )

        return self.async_create_entry(title=data[CONF_HOSTNAME], data=data)


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
