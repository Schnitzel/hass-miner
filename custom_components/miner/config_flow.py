"""Config flow for Miner."""
import logging
from importlib.metadata import version

from .const import PYASIC_VERSION

try:
    import pyasic

    if not version("pyasic") == PYASIC_VERSION:
        raise ImportError
except ImportError:
    from .patch import install_package

    install_package(f"pyasic=={PYASIC_VERSION}")
    import pyasic

from pyasic import MinerNetwork

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_entry_flow import register_discovery_flow
from homeassistant.helpers.selector import TextSelector
from homeassistant.helpers.selector import TextSelectorConfig
from homeassistant.helpers.selector import TextSelectorType

from .const import CONF_IP
from .const import CONF_MIN_POWER
from .const import CONF_MAX_POWER
from .const import CONF_RPC_PASSWORD
from .const import CONF_SSH_PASSWORD
from .const import CONF_SSH_USERNAME
from .const import CONF_TITLE
from .const import CONF_WEB_PASSWORD
from .const import CONF_WEB_USERNAME
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def _async_has_devices(hass: HomeAssistant) -> bool:
    """Return if there are devices that can be discovered."""
    adapters = await network.async_get_adapters(hass)

    for adapter in adapters:
        for ip_info in adapter["ipv4"]:
            local_ip = ip_info["address"]
            network_prefix = ip_info["network_prefix"]
            miner_net = MinerNetwork.from_subnet(f"{local_ip}/{network_prefix}")
            miners = await miner_net.scan()
            if len(miners) > 0:
                return True
    return False


register_discovery_flow(DOMAIN, "miner", _async_has_devices)


async def validate_ip_input(
    data: dict[str, str]
) -> tuple[dict[str, str], pyasic.AnyMiner | None]:
    """Validate the user input allows us to connect."""
    miner_ip = data.get(CONF_IP)

    miner = await pyasic.get_miner(miner_ip)
    if miner is None:
        return {"base": "Unable to connect to Miner, is IP correct?"}, None

    return {}, miner


class MinerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Miner."""

    VERSION = 1

    def __init__(self):
        """Initialize."""
        self._data = {}
        self._miner = None

    async def async_step_user(self, user_input=None):
        """Get miner IP and check if it is available."""
        if user_input is None:
            user_input = {}

        schema = vol.Schema(
            {
                vol.Required(CONF_IP, default=user_input.get(CONF_IP, "")): str,
                vol.Optional(CONF_MIN_POWER, default=100): vol.All(
                    vol.Coerce(int), vol.Range(min=100, max=10000)
                ),
                vol.Optional(CONF_MAX_POWER, default=10000): vol.All(
                    vol.Coerce(int), vol.Range(min=100, max=10000)
                ),
            }
        )

        if not user_input:
            return self.async_show_form(step_id="user", data_schema=schema)

        errors, miner = await validate_ip_input(user_input)

        if errors:
            return self.async_show_form(
                step_id="user", data_schema=schema, errors=errors
            )

        self._miner = miner
        self._data.update(user_input)
        return await self.async_step_login()

    async def async_step_login(self, user_input=None):
        """Get miner login credentials."""
        if user_input is None:
            user_input = {}

        schema_data = {}

        if self._miner.rpc is not None:
            if self._miner.rpc.pwd is not None:
                schema_data[
                    vol.Optional(
                        CONF_RPC_PASSWORD,
                        default=user_input.get(
                            CONF_RPC_PASSWORD,
                            self._miner.rpc.pwd
                            if self._miner.api.pwd is not None
                            else "",
                        ),
                    )
                ] = TextSelector(
                    TextSelectorConfig(
                        type=TextSelectorType.PASSWORD, autocomplete="current-password"
                    )
                )

        if self._miner.web is not None:
            schema_data[
                vol.Optional(
                    CONF_WEB_USERNAME,
                    default=user_input.get(CONF_WEB_USERNAME, self._miner.web.username),
                )
            ] = str
            schema_data[
                vol.Optional(
                    CONF_WEB_PASSWORD,
                    default=user_input.get(
                        CONF_WEB_PASSWORD,
                        self._miner.web.pwd if self._miner.web.pwd is not None else "",
                    ),
                )
            ] = TextSelector(
                TextSelectorConfig(
                    type=TextSelectorType.PASSWORD, autocomplete="current-password"
                )
            )

        if self._miner.ssh is not None:
            schema_data[
                vol.Required(
                    CONF_SSH_USERNAME,
                    default=user_input.get(CONF_SSH_USERNAME, self._miner.ssh.username),
                )
            ] = str
            schema_data[
                vol.Optional(
                    CONF_SSH_PASSWORD,
                    default=user_input.get(
                        CONF_SSH_PASSWORD,
                        self._miner.ssh.pwd if self._miner.ssh.pwd is not None else "",
                    ),
                )
            ] = TextSelector(
                TextSelectorConfig(
                    type=TextSelectorType.PASSWORD, autocomplete="current-password"
                )
            )

        schema = vol.Schema(schema_data)
        if not user_input:
            if len(schema_data) == 0:
                return await self.async_step_title()
            return self.async_show_form(step_id="login", data_schema=schema)

        self._data.update(user_input)
        return await self.async_step_title()

    async def async_step_title(self, user_input=None):
        """Get entity title."""
        if self._miner.api is not None:
            if self._miner.api.pwd is not None:
                self._miner.api.pwd = self._data.get(CONF_RPC_PASSWORD, "")

        if self._miner.web is not None:
            self._miner.web.username = self._data.get(CONF_WEB_USERNAME, "")
            self._miner.web.pwd = self._data.get(CONF_WEB_PASSWORD, "")

        if self._miner.ssh is not None:
            self._miner.ssh.username = self._data.get(CONF_SSH_USERNAME, "")
            self._miner.ssh.pwd = self._data.get(CONF_SSH_PASSWORD, "")

        title = await self._miner.get_hostname()

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

        self._data.update(user_input)

        return self.async_create_entry(title=self._data[CONF_TITLE], data=self._data)
