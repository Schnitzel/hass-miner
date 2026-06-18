"""DataUpdateCoordinator for ASIC Miner."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
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
        entry_id: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.ip = ip
        self.username = username
        self.password = password

        # ── Offline resilience: cached device profile ──────────────────────
        # Persisted via Store (NOT entry.data — writing entry.data would trigger
        # the options update listener and a reload-loop). Lets the entry LOAD
        # with entities (showing unavailable) even when the miner is unreachable
        # at HA startup. Populated from a successful poll; read as a fallback
        # when live ``data`` is None.
        self._store: Store = Store(hass, 1, f"{DOMAIN}_profile_{entry_id}")
        self.profile: dict | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{ip}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    # ── Cached device profile (offline resilience) ─────────────────────────

    async def async_load_profile(self) -> None:
        """Load the persisted device profile (None if no file exists yet).

        Called from __init__.py before the first refresh so that platforms can
        enumerate per-board / per-fan entities from cache when the miner is
        offline at startup.
        """
        self.profile = await self._store.async_load()

    async def _async_store_profile(self, data: MinerData) -> None:
        """Persist a fresh profile derived from a successful poll, if changed."""
        profile = {
            "mac": data.mac,
            "make": data.device_info.make,
            "model": data.device_info.model,
            "fw": data.firmware_version,
            "board_positions": [b.position for b in data.hashboards],
            "fan_positions": [f.position for f in data.fans],
            "psu_fan_positions": [f.position for f in data.psu_fans],
        }
        if profile != self.profile:
            self.profile = profile
            await self._store.async_save(profile)

    # Helper properties: prefer live ``data``, fall back to the cached profile,
    # finally a safe default. Used by entity.py and the platform setups so they
    # work identically online and offline-with-cache.

    @property
    def device_mac(self) -> str | None:
        data = self.data
        if data is not None and data.mac:
            return data.mac
        if self.profile:
            return self.profile.get("mac")
        return None

    @property
    def device_make(self) -> str | None:
        data = self.data
        if data is not None and data.device_info.make:
            return data.device_info.make
        if self.profile:
            return self.profile.get("make")
        return None

    @property
    def device_model(self) -> str | None:
        data = self.data
        if data is not None and data.device_info.model:
            return data.device_info.model
        if self.profile:
            return self.profile.get("model")
        return None

    @property
    def fw_version(self) -> str | None:
        data = self.data
        if data is not None and data.firmware_version:
            return data.firmware_version
        if self.profile:
            return self.profile.get("fw")
        return None

    @property
    def board_positions(self) -> list[int]:
        data = self.data
        if data is not None:
            return [b.position for b in data.hashboards]
        if self.profile:
            return list(self.profile.get("board_positions") or [])
        return []

    @property
    def fan_positions(self) -> list[int]:
        data = self.data
        if data is not None:
            return [f.position for f in data.fans]
        if self.profile:
            return list(self.profile.get("fan_positions") or [])
        return []

    @property
    def psu_fan_positions(self) -> list[int]:
        data = self.data
        if data is not None:
            return [f.position for f in data.psu_fans]
        if self.profile:
            return list(self.profile.get("psu_fan_positions") or [])
        return []

    # ── Setup / update ─────────────────────────────────────────────────────

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
            data = await self.miner.get_data()
        except Exception as err:
            raise UpdateFailed(
                f"Error communicating with miner at {self.ip}: {err}"
            ) from err

        # Persist a fresh device profile so the entry can load offline next time.
        await self._async_store_profile(data)
        return data
