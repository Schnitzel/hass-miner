"""Config flow for Miner."""
import logging

import pyasic
import voluptuous as vol
from homeassistant import config_entries, exceptions
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_IP, CONF_PASSWORD, CONF_TITLE, CONF_USERNAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

# async def _async_has_devices(hass: HomeAssistant) -> bool:
#     """Return if there are devices that can be discovered."""
#     # TODO Check if there are any devices that can be discovered in the network.
#     devices = await hass.async_add_executor_job(my_pypi_dependency.discover)
#     return len(devices) > 0


# config_entry_flow.register_discovery_flow(DOMAIN, "Miner", _async_has_devices)


async def validate_input(data: dict[str, str]) -> dict[str, str]:
    """Validate the user input allows us to connect."""
    miner_ip = data.get(CONF_IP)
    miner_username = data.get(CONF_USERNAME)
    miner_password = data.get(CONF_PASSWORD)

    miner = await pyasic.get_miner(miner_ip)
    if miner is None:
        return {"base": "Unable to connect to Miner, is IP correct?"}

    miner.username = miner_username
    miner.pwd = miner_password
    await miner.get_data(include=["mac"])

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
                vol.Required(
                    CONF_USERNAME, default=user_input.get(CONF_USERNAME, "root")
                ): str,
                vol.Optional(
                    CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, "")
                ): TextSelector(
                    TextSelectorConfig(
                        type=TextSelectorType.PASSWORD, autocomplete="current-password"
                    )
                ),
            }
        )
        if not user_input:
            return self.async_show_form(step_id="user", data_schema=schema)

        errors = await validate_input(user_input)

        if not errors:
            self._data.update(user_input)
            return await self.async_step_title()

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_title(self, user_input=None):
        """Ask for Entity Title."""

        miner_ip = self._data.get(CONF_IP)
        miner = await pyasic.get_miner(miner_ip)  # should be fast, cached
        title = await miner.get_hostname()

        if user_input is None:
            user_input = {}

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_TITLE,
                    default=user_input.get(CONF_TITLE, title),
                ): str,
            }
        )
        if not user_input:
            return self.async_show_form(step_id="title", data_schema=data_schema)

        data = {**self._data, **user_input}

        return self.async_create_entry(title=data[CONF_TITLE], data=data)


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
