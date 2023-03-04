"""IoTaWatt DataUpdateCoordinator."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed
from pyasic.API import APIError
from pyasic.miners import BaseMiner
from pyasic.miners.miner_factory import MinerFactory

from .const import CONF_IP

_LOGGER = logging.getLogger(__name__)

# Matches iotwatt data log interval
REQUEST_REFRESH_DEFAULT_COOLDOWN = 5


class MinerCoordinator(DataUpdateCoordinator):
    """Class to manage fetching update data from the IoTaWatt Energy Device."""

    miner: BaseMiner | None = None

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

        try:
            if self.miner is None:
                self.miner = await MinerFactory().get_miner(miner_ip)
            miner_data = await self.miner.get_data()

        except APIError as err:
            raise UpdateFailed("API Error") from err

        data = {
            "hostname": miner_data.hostname,
            "mac": miner_data.mac,
            "make": miner_data.make,
            "model": miner_data.model,
            "ip": self.miner.ip,
            "miner_sensors": {
                "hashrate": int(miner_data.hashrate),
                "temperature": int(miner_data.temperature_avg),
                "power_limit": miner_data.wattage_limit,
                "miner_consumption": miner_data.wattage,
                "scaled_power_limit": None,
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
        # data["hostname"] = self.entry.data[CONF_HOSTNAME]
        # data["version"] = miner_data.version

        if "tunerstatus" in self.miner.api.get_commands():
            tuner_data = await self.miner.api.tunerstatus()

            tuner = tuner_data.get("TUNERSTATUS")
            if tuner:
                if len(tuner) > 0:
                    dynamic_power_scaling = tuner[0].get("DynamicPowerScaling")
                    if isinstance(dynamic_power_scaling, dict):
                        scaled_power_limit = dynamic_power_scaling.get(
                            "ScaledPowerLimit"
                        )
                        if scaled_power_limit:
                            data["miner_sensors"][
                                "scaled_power_limit"
                            ] = scaled_power_limit
                    elif dynamic_power_scaling == "InitialPowerLimit":
                        data["miner_sensors"][
                            "scaled_power_limit"
                        ] = miner_data.wattage_limit

        return data
