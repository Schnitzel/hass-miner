"""IoTaWatt DataUpdateCoordinator."""
from __future__ import annotations

import ipaddress
import logging
from datetime import timedelta

from API import APIError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed
from miners import BaseMiner
from miners.miner_factory import MinerFactory

from .const import CONF_HOSTNAME
from .const import CONF_IP

_LOGGER = logging.getLogger(__name__)

# Matches iotwatt data log interval
REQUEST_REFRESH_DEFAULT_COOLDOWN = 5


class MinerCoordinator(DataUpdateCoordinator):
    """Class to manage fetching update data from the IoTaWatt Energy Device."""

    miner_factory: MinerFactory | None = None
    miner: BaseMiner | None = None

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, miner_factory: MinerFactory
    ) -> None:
        """Initialize MinerCoordinator object."""
        self.entry = entry
        self.miner_factory = miner_factory
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

        miner_ip = ipaddress.ip_address(self.entry.data[CONF_IP])
        miner_api_data = {}
        model = {}

        try:
            if self.miner is None:
                self.miner = await self.miner_factory.get_miner(miner_ip)
            miner_api_data = await self.miner.api.multicommand(
                "summary", "temps", "tunerstatus", "devs", "fans"
            )
            model = await self.miner.get_model()

        except APIError as err:
            raise UpdateFailed("API Error") from err

        data = {}
        data["hostname"] = self.entry.data[CONF_HOSTNAME]
        data["model"] = model
        data["ip"] = self.miner.ip
        # data["version"] = miner_version
        data["miner_sensors"] = {}

        summary = miner_api_data.get("summary")[0].get("SUMMARY")
        hashrate = summary[0].get("MHS 1m")
        if hashrate:
            data["miner_sensors"]["hashrate"] = round(hashrate / 1000000, 2)

        temps = miner_api_data.get("temps")[0].get("TEMPS")
        data["board_sensors"] = {}
        chip_temps = [0]
        if temps:
            for temp_hashboard in temps:
                if not temp_hashboard["ID"] in data["board_sensors"]:
                    data["board_sensors"][temp_hashboard["ID"]] = {}
                data["board_sensors"][temp_hashboard["ID"]][
                    "board_temperature"
                ] = temp_hashboard["Board"]
                data["board_sensors"][temp_hashboard["ID"]][
                    "chip_temperature"
                ] = temp_hashboard["Chip"]
                chip_temps.append(temp_hashboard["Chip"])

        data["miner_sensors"]["temperature"] = max(chip_temps)

        tuner = miner_api_data.get("tunerstatus")[0].get("TUNERSTATUS")
        if tuner:
            if len(tuner) > 0:
                power_limit = tuner[0].get("PowerLimit")
                if power_limit:
                    data["miner_sensors"]["power_limit"] = power_limit
                miner_consumption = tuner[0].get("ApproximateMinerPowerConsumption")
                if miner_consumption:
                    data["miner_sensors"]["miner_consumption"] = miner_consumption
                else:
                    data["miner_sensors"]["miner_consumption"] = None
                dynamic_power_scaling = tuner[0].get("DynamicPowerScaling")
                if isinstance(dynamic_power_scaling, dict):
                    scaled_power_limit = dynamic_power_scaling.get("ScaledPowerLimit")
                    if scaled_power_limit:
                        data["miner_sensors"]["scaled_power_limit"] = scaled_power_limit
                    else:
                        data["miner_sensors"]["scaled_power_limit"] = None
                elif dynamic_power_scaling == "InitialPowerLimit":
                    data["miner_sensors"]["scaled_power_limit"] = power_limit
                else:
                    data["miner_sensors"]["scaled_power_limit"] = None

        devs = miner_api_data.get("devs")[0].get("DEVS")
        if devs:
            for hashboard in devs:
                if not hashboard["ID"] in data["board_sensors"]:
                    data["board_sensors"][hashboard["ID"]] = {}
                data["board_sensors"][hashboard["ID"]]["board_hashrate"] = round(
                    hashboard["MHS 1m"] / 1000000, 2
                )

        return data
