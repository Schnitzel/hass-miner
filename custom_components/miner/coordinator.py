"""IoTaWatt DataUpdateCoordinator."""
import logging
from datetime import timedelta
from typing import Union

import pyasic
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import CONF_IP

_LOGGER = logging.getLogger(__name__)

# Matches iotwatt data log interval
REQUEST_REFRESH_DEFAULT_COOLDOWN = 5


class MinerCoordinator(DataUpdateCoordinator):
    """Class to manage fetching update data from the IoTaWatt Energy Device."""

    miner: Union[pyasic.AnyMiner, None] = None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize MinerCoordinator object."""
        self.entry = entry
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=entry.title, # hostname for now
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

        try:
            if self.miner is None:
                self.miner = await pyasic.get_miner(miner_ip)
            miner_data = await self.miner.get_data()

        except pyasic.APIError as err:
            raise UpdateFailed("API Error") from err

        data = {
            "hostname": miner_data.hostname,
            "mac": miner_data.mac,
            "make": miner_data.make,
            "model": miner_data.model,
            "ip": self.miner.ip,
            "is_mining": miner_data.is_mining,
            "miner_sensors": {
                "hashrate": miner_data.hashrate,
                "ideal_hashrate": miner_data.nominal_hashrate,
                "temperature": int(miner_data.temperature_avg),
                "power_limit": miner_data.wattage_limit,
                "miner_consumption": miner_data.wattage,
            },
            "board_sensors": {
                board.slot: {
                    "board_temperature": board.temp,
                    "chip_temperature": board.chip_temp,
                    "board_hashrate": board.hashrate,
                }
                for board in miner_data.hashboards
            },
        }

        return data
