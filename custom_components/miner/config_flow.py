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
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from pyasic_rs import MinerFactory

from .const import (
    CONF_BOOT_TIMEOUT,
    CONF_ONLY_AVAILABLE,
    CONF_POWER_ENTITY,
    CONF_SCAN_INTERVAL,
    CONF_SENSOR_CATEGORIES,
    DEFAULT_BOOT_TIMEOUT,
    DEFAULT_ONLY_AVAILABLE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SENSOR_CATEGORIES,
    DOMAIN,
    MAX_BOOT_TIMEOUT,
    MAX_SCAN_INTERVAL,
    MIN_BOOT_TIMEOUT,
    MIN_SCAN_INTERVAL,
    SENSOR_CATEGORIES,
)

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
    title = f"{miner.make} {miner.model} ({ip})"
    return miner, title


class AsicMinerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ASIC Miner."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AsicMinerOptionsFlow:
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
    """Options flow — sensor categories, only-available, poll interval, web password.

    * **Sensor categories**: tick the groups of sensors to create. Unticking a
      category removes its entities on reload (deterministic / boot-safe).
    * **Only type-relevant sensors**: hide values that don't apply to this miner
      (e.g. fluid/water temps on air-cooled, chip temp where unreported).
    * **Scan interval**: how often the miner is polled.
    * **Firmware web password** (BETA): lets the VNish preset/throttle controls
      obtain an unlock token without re-adding the miner.

    Note: HA provides ``self.config_entry`` automatically; do not assign it
    (it is a read-only property in current HA).
    """

    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is not None:
            # Merge over existing options so unrelated keys are preserved.
            data = {**self.config_entry.options, **user_input}
            # An empty/unselected power entity must DISABLE power-aware polling,
            # not silently keep a previously-set value (the merge would otherwise
            # preserve it). Treat empty/absent as "cleared".
            if not user_input.get(CONF_POWER_ENTITY):
                data.pop(CONF_POWER_ENTITY, None)
            return self.async_create_entry(title="", data=data)

        options = self.config_entry.options
        current_password = options.get(
            CONF_PASSWORD, self.config_entry.data.get(CONF_PASSWORD, "")
        )
        current_categories = options.get(
            CONF_SENSOR_CATEGORIES, DEFAULT_SENSOR_CATEGORIES
        )
        current_only_available = options.get(
            CONF_ONLY_AVAILABLE, DEFAULT_ONLY_AVAILABLE
        )
        current_scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        current_power_entity = options.get(CONF_POWER_ENTITY, "")
        current_boot_timeout = options.get(CONF_BOOT_TIMEOUT, DEFAULT_BOOT_TIMEOUT)

        categories_select = SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=cat, label=cat)
                    for cat in SENSOR_CATEGORIES
                ],
                translation_key=CONF_SENSOR_CATEGORIES,
                multiple=True,
                mode=SelectSelectorMode.LIST,
            )
        )
        scan_interval_select = NumberSelector(
            NumberSelectorConfig(
                min=MIN_SCAN_INTERVAL,
                max=MAX_SCAN_INTERVAL,
                step=1,
                unit_of_measurement="s",
                mode=NumberSelectorMode.BOX,
            )
        )
        power_entity_select = EntitySelector(
            EntitySelectorConfig(
                domain=["switch", "binary_sensor", "input_boolean"]
            )
        )
        boot_timeout_select = NumberSelector(
            NumberSelectorConfig(
                min=MIN_BOOT_TIMEOUT,
                max=MAX_BOOT_TIMEOUT,
                step=5,
                unit_of_measurement="s",
                mode=NumberSelectorMode.BOX,
            )
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SENSOR_CATEGORIES, default=current_categories
                    ): categories_select,
                    vol.Optional(
                        CONF_ONLY_AVAILABLE, default=current_only_available
                    ): BooleanSelector(),
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=current_scan_interval
                    ): scan_interval_select,
                    # EntitySelector: no hard default — pass the current value via
                    # suggested_value so submitting without a selection simply
                    # omits the key (key absent ⇒ power-aware polling disabled).
                    vol.Optional(
                        CONF_POWER_ENTITY,
                        description={"suggested_value": current_power_entity or None},
                    ): power_entity_select,
                    vol.Optional(
                        CONF_BOOT_TIMEOUT, default=current_boot_timeout
                    ): boot_timeout_select,
                    vol.Optional(CONF_PASSWORD, default=current_password): str,
                }
            ),
        )
