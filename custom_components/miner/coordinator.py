"""DataUpdateCoordinator for ASIC Miner."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from pyasic_rs import MinerFactory
from pyasic_rs.data import MinerData
from pyasic_rs.miner import Miner

from . import vnish
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

        # BETA VNish control state (populated only for VNish miners).
        self.is_vnish: bool = False
        self.vnish_presets: list[str] = []
        self.vnish_preset: str | None = None
        self.vnish_throttle: int | None = None

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

        # BETA: detect VNish firmware so the preset/throttle entities get added.
        session = async_get_clientsession(self.hass)
        self.is_vnish = await vnish.detect_vnish(session, self.ip)
        if self.is_vnish and self.password:
            self.vnish_presets = await vnish.fetch_presets(
                session, self.ip, self.password
            )
        if self.is_vnish and not self.vnish_presets:
            self.vnish_presets = list(vnish.FALLBACK_PRESETS)

    async def _async_update_data(self) -> MinerData:
        if self.miner is None:
            await self._async_setup()
        try:
            data = await self.miner.get_data()
        except Exception as err:
            raise UpdateFailed(
                f"Error communicating with miner at {self.ip}: {err}"
            ) from err
        if self.is_vnish:
            await self._async_update_vnish()
        return data

    async def _async_update_vnish(self) -> None:
        """BETA: refresh VNish preset/throttle. Never fails the main update."""
        session = async_get_clientsession(self.hass)
        try:
            self.vnish_throttle = await vnish.fetch_throttle(session, self.ip)
            if self.password:
                self.vnish_preset = await vnish.fetch_current_preset(
                    session, self.ip, self.password
                )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("VNish extra-poll failed for %s: %s", self.ip, err)
