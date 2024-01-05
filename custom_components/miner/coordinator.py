"""Miner DataUpdateCoordinator."""
import logging
from datetime import timedelta

import pyasic
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_IP, CONF_PASSWORD, CONF_USERNAME

_LOGGER = logging.getLogger(__name__)

# Matches iotwatt data log interval
REQUEST_REFRESH_DEFAULT_COOLDOWN = 5


class MinerCoordinator(DataUpdateCoordinator):
    """Class to manage fetching update data from the Miner."""

    miner: pyasic.AnyMiner = None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize MinerCoordinator object."""
        self.entry = entry
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=entry.title,
            update_interval=timedelta(seconds=10),
            request_refresh_debouncer=Debouncer(
                hass,
                _LOGGER,
                cooldown=REQUEST_REFRESH_DEFAULT_COOLDOWN,
                immediate=True,
            ),
        )

    async def _async_update_data(self):
        """Fetch sensors from miners."""

        miner_ip = self.entry.data[CONF_IP]
        miner_username = self.entry.data[CONF_USERNAME]
        miner_password = self.entry.data[CONF_PASSWORD]

        try:
            if self.miner is None:
                self.miner = await pyasic.get_miner(miner_ip)
                self.miner.username = miner_username
                self.miner.pwd = miner_password

            miner_data = await self.miner.get_data(
                include=[
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
                ]
            )

        except pyasic.APIError as err:
            raise UpdateFailed("API Error") from err

        except Exception as err:
            raise UpdateFailed("API Error") from err

        _LOGGER.debug(miner_data)

        data = {
            "hostname": miner_data.hostname,
            "mac": miner_data.mac,
            "make": miner_data.make,
            "model": miner_data.model,
            "ip": self.miner.ip,
            "is_mining": miner_data.is_mining,
            "fw_ver": miner_data.fw_ver,
            "miner_sensors": {
                "hashrate": miner_data.hashrate,
                "ideal_hashrate": miner_data.expected_hashrate,
                "temperature": miner_data.temperature_avg,
                "power_limit": miner_data.wattage_limit,
                "miner_consumption": miner_data.wattage,
                "efficiency": miner_data.efficiency,
            },
            "board_sensors": {
                board.slot: {
                    "board_temperature": board.temp,
                    "chip_temperature": board.chip_temp,
                    "board_hashrate": board.hashrate,
                }
                for board in miner_data.hashboards
            },
            "fan_sensors": {
                idx: {"fan_speed": fan.speed} for idx, fan in enumerate(miner_data.fans)
            },
        }
        return data
