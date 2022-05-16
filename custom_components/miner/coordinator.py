"""IoTaWatt DataUpdateCoordinator."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging

from miners.miner_factory import MinerFactory
from miners import BaseMiner

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import httpx_client
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_IP, CONF_HOSTNAME

from API import APIError
import ipaddress

from .parse_data import safe_parse_api_data

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
        miner_data = {}

        try:
            if self.miner is None:
                self.miner = await self.miner_factory.get_miner(miner_ip)
            miner_data = await self.miner.get_data()
            # miner_version = await self.miner.get_version()
            tunerstatus = await self.miner.api.tunerstatus()
        except APIError as err:
            raise UpdateFailed("API Error") from err

        data = {}
        data["hostname"] = self.entry.data[CONF_HOSTNAME]
        data["model"] = miner_data["Model"]
        data["ip"] = miner_data["IP"]
        # data["version"] = miner_version
        data["sensors"] = {}
        data["sensors"]["temperature"] = miner_data["Temperature"]
        data["sensors"]["hashrate"] = miner_data["Hashrate"]

        data["number"] = {}
        tuner = tunerstatus.get("TUNERSTATUS")
        if tuner:
            if len(tuner) > 0:
                power_limit = tuner[0].get("PowerLimit")
                if power_limit:
                    data["number"]["power_limit"] = power_limit
                miner_consumption = tuner[0].get("ApproximateMinerPowerConsumption")
                if miner_consumption:
                    data["sensors"]["miner_consumption"] = miner_consumption
                else:
                    data["sensors"]["miner_consumption"] = None
                dynamic_power_scaling = tuner[0].get("DynamicPowerScaling")
                if dynamic_power_scaling == "InitialPowerLimit":
                    data["sensors"]["scaled_power_limit"] = power_limit
                else:
                    scaled_power_limit = dynamic_power_scaling.get("ScaledPowerLimit")
                    if scaled_power_limit:
                        data["sensors"]["scaled_power_limit"] = scaled_power_limit
                    else:
                        data["sensors"]["scaled_power_limit"] = None

        return data
