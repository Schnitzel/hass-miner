"""DataUpdateCoordinator for ASIC Miner."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from pyasic_rs import MinerFactory
from pyasic_rs.data import MinerData
from pyasic_rs.miner import Miner

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class MinerCoordinator(DataUpdateCoordinator[MinerData]):
    """Coordinator that polls a single ASIC miner via pyasic-rs."""

    miner: Miner | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        ip: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.ip = ip
        self.username = username
        self.password = password

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{ip}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_setup(self) -> None:
        factory = MinerFactory()
        miner = await factory.get_miner(self.ip)
        if miner is None:
            raise UpdateFailed(f"Could not identify miner at {self.ip}")
        if self.username and self.password:
            miner.set_auth(self.username, self.password)
        self.miner = miner

    async def _async_update_data(self) -> MinerData:
        if self.miner is None:
            await self._async_setup()
        try:
            return await self.miner.get_data()
        except Exception as err:
            raise UpdateFailed(
                f"Error communicating with miner at {self.ip}: {err}"
            ) from err
