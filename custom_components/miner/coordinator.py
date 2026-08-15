"""Miner DataUpdateCoordinator."""
import logging
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyasic

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import CONF_IP
from .const import CONF_MAC
from .const import CONF_MIN_POWER
from .const import CONF_MAX_POWER
from .const import CONF_RPC_PASSWORD
from .const import CONF_SSH_PASSWORD
from .const import CONF_SSH_USERNAME
from .const import CONF_WEB_PASSWORD
from .const import CONF_WEB_USERNAME

_LOGGER = logging.getLogger(__name__)

# Matches iotwatt data log interval
REQUEST_REFRESH_DEFAULT_COOLDOWN = 5

DEFAULT_DATA = {
    "hostname": None,
    "mac": None,
    "make": None,
    "model": None,
    "ip": None,
    "is_mining": False,
    "fw_ver": None,
    "miner_sensors": {
        "hashrate": 0,
        "ideal_hashrate": 0,
        "active_preset_name": None,
        "temperature": 0,
        "power_limit": 0,
        "miner_consumption": 0,
        "efficiency": 0.0,
    },
    "board_sensors": {},
    "fan_sensors": {},
    "config": {},
}


def _offline_data(entry: ConfigEntry) -> dict:
    """Zeroed data for an unreachable miner, keeping the pinned MAC."""
    return {
        **DEFAULT_DATA,
        "mac": entry.data.get(CONF_MAC),
        "power_limit_range": {
            "min": entry.data.get(CONF_MIN_POWER, 15),
            "max": entry.data.get(CONF_MAX_POWER, 10000),
        },
    }


class MinerCoordinator(DataUpdateCoordinator):
    """Class to manage fetching update data from the Miner."""

    miner: "pyasic.AnyMiner" = None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize MinerCoordinator object."""
        self.miner = None
        self._failure_count = 0
        self._ever_succeeded = False
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=timedelta(seconds=10),
            request_refresh_debouncer=Debouncer(
                hass,
                _LOGGER,
                cooldown=REQUEST_REFRESH_DEFAULT_COOLDOWN,
                immediate=True,
            ),
        )

    @property
    def available(self):
        """Return if device is available or not."""
        return self.miner is not None

    async def get_miner(self):
        """Get a valid Miner instance."""
        import pyasic  # lazy import to avoid blocking event loop

        miner_ip = self.config_entry.data[CONF_IP]
        miner = await pyasic.get_miner(miner_ip)
        if miner is None:
            return None

        self.miner = miner
        if self.miner.api is not None:
            if self.miner.api.pwd is not None:
                self.miner.api.pwd = self.config_entry.data.get(CONF_RPC_PASSWORD, "")

        if self.miner.web is not None:
            self.miner.web.username = self.config_entry.data.get(CONF_WEB_USERNAME, "")
            self.miner.web.pwd = self.config_entry.data.get(CONF_WEB_PASSWORD, "")

        if self.miner.ssh is not None:
            self.miner.ssh.username = self.config_entry.data.get(CONF_SSH_USERNAME, "")
            self.miner.ssh.pwd = self.config_entry.data.get(CONF_SSH_PASSWORD, "")
        return self.miner

    def _handle_failure(self, reason: str, err: Exception | None = None) -> dict:
        """Handle a failed poll.

        During initial setup we must never hand back placeholder data: entities
        would be created with ``mac=None`` unique_ids and a second device would
        appear once the miner answers properly (issue #593). Raise
        ConfigEntryNotReady so HA retries setup instead.

        After setup, tolerate a single failure (return zeroed data so totals stay
        sane, issue #538) and mark unavailable on consecutive failures.
        """
        if not self._ever_succeeded:
            raise ConfigEntryNotReady(reason) from err

        self._failure_count += 1
        if self._failure_count == 1:
            _LOGGER.warning("%s - returning zeroed data (first failure).", reason)
            return _offline_data(self.config_entry)
        raise UpdateFailed(reason) from err

    async def _async_update_data(self):
        """Fetch sensors from miners."""
        import pyasic  # lazy import to avoid blocking event loop

        miner = await self.get_miner()

        if miner is None:
            return self._handle_failure("Miner Offline")

        # At this point, miner is valid
        _LOGGER.debug(f"Found miner: {self.miner}")

        # Base data options to fetch
        data_options = [
            pyasic.DataOptions.HOSTNAME,
            pyasic.DataOptions.MAC,
            pyasic.DataOptions.IS_MINING,
            pyasic.DataOptions.FW_VERSION,
            pyasic.DataOptions.HASHRATE,
            pyasic.DataOptions.EXPECTED_HASHRATE,
            pyasic.DataOptions.HASHBOARDS,
            pyasic.DataOptions.WATTAGE,
            pyasic.DataOptions.WATTAGE_LIMIT,
            pyasic.DataOptions.FANS,
            pyasic.DataOptions.CONFIG,
        ]

        try:
            miner_data = await self.miner.get_data(include=data_options)
        except Exception as err:
            # VNish firmware has a bug with CONFIG - retry without it
            if "config" not in str(err).lower():
                return self._handle_failure(f"Error fetching miner data: {err}", err)
            _LOGGER.warning(
                f"Config fetch failed for {self.miner}, retrying without CONFIG: {err}"
            )
            data_options.remove(pyasic.DataOptions.CONFIG)
            try:
                miner_data = await self.miner.get_data(include=data_options)
            except Exception as retry_err:
                return self._handle_failure(
                    f"Error fetching miner data: {retry_err}", retry_err
                )

        _LOGGER.debug(f"Got data: {miner_data}")

        # Pin the MAC: it is the unique_id/device identifier for every entity.
        # A miner that is still booting can answer with mac=None; fall back to
        # the MAC we saw earlier rather than creating a second device (#593).
        mac = miner_data.mac or self.config_entry.data.get(CONF_MAC)
        if mac is None:
            return self._handle_failure("Miner did not report a MAC address yet")
        if self.config_entry.data.get(CONF_MAC) != mac:
            self.hass.config_entries.async_update_entry(
                self.config_entry, data={**self.config_entry.data, CONF_MAC: mac}
            )

        # Success: reset the failure count
        self._failure_count = 0
        self._ever_succeeded = True

        try:
            hashrate = round(float(miner_data.hashrate), 2)
        except TypeError:
            hashrate = None

        try:
            expected_hashrate = round(float(miner_data.expected_hashrate), 2)
        except TypeError:
            expected_hashrate = None

        try:
            active_preset = miner_data.config.mining_mode.active_preset.name
        except AttributeError:
            active_preset = None

        data = {
            "hostname": miner_data.hostname,
            "mac": mac,
            "make": miner_data.make,
            "model": miner_data.model,
            "ip": self.miner.ip,
            "is_mining": miner_data.is_mining,
            "fw_ver": miner_data.fw_ver,
            "miner_sensors": {
                "hashrate": hashrate,
                "ideal_hashrate": expected_hashrate,
                "active_preset_name": active_preset,
                "temperature": miner_data.temperature_avg,
                "power_limit": miner_data.wattage_limit,
                "miner_consumption": miner_data.wattage,
                "efficiency": miner_data.efficiency_fract,
            },
            "board_sensors": {
                board.slot: {
                    "board_temperature": board.temp,
                    "chip_temperature": board.chip_temp,
                    "board_hashrate": round(float(board.hashrate or 0), 2),
                }
                for board in miner_data.hashboards
            },
            "fan_sensors": {
                idx: {"fan_speed": fan.speed} for idx, fan in enumerate(miner_data.fans)
            },
            "config": miner_data.config,
            "power_limit_range": {
                "min": self.config_entry.data.get(CONF_MIN_POWER, 15),
                "max": self.config_entry.data.get(CONF_MAX_POWER, 10000),
            },
        }
        return data
