"""Config flow for ASIC Miner integration."""

from __future__ import annotations

import asyncio
import ipaddress

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.network import async_get_adapters
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from pyasic_rs import MinerFactory

from .const import DOMAIN

CONF_SUBNET = "subnet"
CONF_SELECTED_MINER = "selected_miner"

STEP_MANUAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_USERNAME, default=""): str,
        vol.Optional(CONF_PASSWORD, default=""): str,
    }
)

STEP_CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_USERNAME, default=""): str,
        vol.Optional(CONF_PASSWORD, default=""): str,
    }
)


async def _default_subnet(hass) -> str:
    """Return the local subnet from HA's network info, or a safe fallback."""
    try:
        adapters = await async_get_adapters(hass)
        for adapter in adapters:
            if adapter.get("default") and adapter.get("ipv4"):
                ip_info = adapter["ipv4"][0]
                network = ipaddress.IPv4Network(
                    f"{ip_info['address']}/{ip_info['network_prefix']}", strict=False
                )
                return str(network)
    except Exception:  # noqa: BLE001
        pass
    return "192.168.1.0/24"


async def _connect_and_title(ip: str, username: str = "", password: str = "") -> tuple:
    """Connect to a miner and return (miner, title). Raises ConnectionError on failure."""
    factory = MinerFactory()
    miner = await factory.get_miner(ip)
    if miner is None:
        raise ConnectionError
    if username and password:
        miner.set_auth(username, password)
    data = await miner.get_data()
    # pyasic-rs 0.6.0: DeviceInfo exposes fields via model_dump(), not attrs.
    di = data.device_info.model_dump()
    title = f"{di.get('make')} {di.get('model')} ({ip})"
    return miner, title


class AsicMinerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ASIC Miner."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "AsicMinerOptionsFlow":
        return AsicMinerOptionsFlow()

    def __init__(self) -> None:
        self._subnet: str = ""
        self._discovered: dict[str, str] = {}  # ip -> "Make Model (ip)"
        self._scan_task: asyncio.Task | None = None
        self._selected_ip: str = ""

    # ── Entry point: menu ─────────────────────────────────────────────────

    async def async_step_user(self, user_input=None) -> FlowResult:
        return self.async_show_menu(
            step_id="user",
            menu_options=["manual", "scan"],
        )

    # ── Manual path ───────────────────────────────────────────────────────

    async def async_step_manual(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            ip = user_input[CONF_HOST]
            username = user_input.get(CONF_USERNAME) or ""
            password = user_input.get(CONF_PASSWORD) or ""
            try:
                _, title = await _connect_and_title(ip, username, password)
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(ip)
                self._abort_if_unique_id_configured()
                data = {CONF_HOST: ip}
                if username:
                    data[CONF_USERNAME] = username
                if password:
                    data[CONF_PASSWORD] = password
                return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="manual",
            data_schema=STEP_MANUAL_SCHEMA,
            errors=errors,
        )

    # ── Scan path: subnet form ────────────────────────────────────────────

    async def async_step_scan(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._subnet = user_input[CONF_SUBNET]
            return await self.async_step_scanning()

        default = await _default_subnet(self.hass)
        return self.async_show_form(
            step_id="scan",
            data_schema=vol.Schema({vol.Required(CONF_SUBNET, default=default): str}),
        )

    # ── Scan path: progress ───────────────────────────────────────────────

    async def async_step_scanning(self, user_input=None) -> FlowResult:
        if self._scan_task is None:
            self._scan_task = self.hass.async_create_task(self._do_scan(self._subnet))

        if not self._scan_task.done():
            return self.async_show_progress(
                step_id="scanning",
                progress_action="scanning",
                progress_task=self._scan_task,
            )

        self._scan_task = None
        return self.async_show_progress_done(next_step_id="pick_miner")

    async def _do_scan(self, subnet: str) -> None:
        """Populate self._discovered by scanning the subnet."""
        self._discovered = {}
        try:
            factory = MinerFactory.from_subnet(subnet)
            async for ip, miner in factory.scan_stream_with_ip():
                if miner is not None:
                    label = f"{miner.make} {miner.model} ({ip})"
                    self._discovered[str(ip)] = label
        except Exception:  # noqa: BLE001
            pass

    # ── Scan path: pick miner ─────────────────────────────────────────────

    async def async_step_pick_miner(self, user_input=None) -> FlowResult:
        if not self._discovered:
            return self.async_show_form(
                step_id="scan",
                data_schema=vol.Schema(
                    {vol.Required(CONF_SUBNET, default=self._subnet): str}
                ),
                errors={"base": "no_miners_found"},
            )

        if user_input is not None:
            self._selected_ip = user_input[CONF_SELECTED_MINER]
            return await self.async_step_credentials()

        return self.async_show_form(
            step_id="pick_miner",
            data_schema=vol.Schema(
                {vol.Required(CONF_SELECTED_MINER): vol.In(self._discovered)}
            ),
        )

    # ── Scan path: credentials ────────────────────────────────────────────

    async def async_step_credentials(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input.get(CONF_USERNAME) or ""
            password = user_input.get(CONF_PASSWORD) or ""
            try:
                _, title = await _connect_and_title(
                    self._selected_ip, username, password
                )
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(self._selected_ip)
                self._abort_if_unique_id_configured()
                data = {CONF_HOST: self._selected_ip}
                if username:
                    data[CONF_USERNAME] = username
                if password:
                    data[CONF_PASSWORD] = password
                return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="credentials",
            data_schema=STEP_CREDENTIALS_SCHEMA,
            description_placeholders={"host": self._selected_ip},
            errors=errors,
        )


class AsicMinerOptionsFlow(config_entries.OptionsFlow):
    """Options flow — set/update the firmware web password post-setup.

    BETA: needed so the VNish preset/throttle controls can obtain an unlock
    token without re-adding the miner (which would recreate all entities).

    Note: HA provides ``self.config_entry`` automatically; do not assign it
    (it is a read-only property in current HA).
    """

    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_PASSWORD, self.config_entry.data.get(CONF_PASSWORD, "")
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Optional(CONF_PASSWORD, default=current): str}
            ),
        )
