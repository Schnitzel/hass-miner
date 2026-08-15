"""Shared fixtures."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.miner.const import (
    CONF_IP,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_TITLE,
    DOMAIN,
)

MAC = "AA:BB:CC:DD:EE:FF"
IP = "192.168.1.50"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom_components in tests."""
    yield


@pytest.fixture(autouse=True)
def no_pyasic_install():
    """Never hit the network / uv during tests; pyasic is installed in the venv."""
    with patch("custom_components.miner.patch.install_package", return_value=True) as m:
        yield m


class FakeBoard:
    def __init__(self, slot, temp=60.0, chip_temp=70.0, hashrate=30.0):
        self.slot = slot
        self.temp = temp
        self.chip_temp = chip_temp
        self.hashrate = hashrate


class FakeFan:
    def __init__(self, speed=4000):
        self.speed = speed


class FakeMinerData:
    """Minimal stand-in for pyasic.MinerData."""

    def __init__(self, mac=MAC, hashrate=90.0, wattage=3000, wattage_limit=3200):
        self.hostname = "miner-1"
        self.mac = mac
        self.make = "AntMiner"
        self.model = "S19"
        self.is_mining = True
        self.fw_ver = "1.0"
        self.hashrate = hashrate
        self.expected_hashrate = 95.0
        self.hashboards = [FakeBoard(0), FakeBoard(1), FakeBoard(2)]
        self.wattage = wattage
        self.wattage_limit = wattage_limit
        self.fans = [FakeFan(), FakeFan()]
        self.config = MagicMock()
        self.config.mining_mode.active_preset.name = "normal"
        self.temperature_avg = 65.0
        self.efficiency_fract = 33.3


def make_fake_miner(data: FakeMinerData | None = None, **kw):
    """Build a fake pyasic miner object."""
    miner = MagicMock()
    miner.ip = IP
    miner.api = None
    miner.web = None
    miner.ssh = None
    miner.rpc = None
    miner.expected_hashboards = 3
    miner.expected_fans = 2
    miner.supports_shutdown = True
    miner.supports_autotuning = True
    miner.get_data = AsyncMock(return_value=data or FakeMinerData())
    miner.get_mac = AsyncMock(return_value=(data or FakeMinerData()).mac)
    miner.get_hostname = AsyncMock(return_value="miner-1")
    miner.set_power_limit = AsyncMock(return_value=True)
    for k, v in kw.items():
        setattr(miner, k, v)
    return miner


@pytest.fixture
def fake_miner():
    return make_fake_miner()


@pytest.fixture
def mock_get_miner(fake_miner):
    """Patch pyasic.get_miner to return the fake miner."""
    with patch("pyasic.get_miner", new=AsyncMock(return_value=fake_miner)) as m:
        yield m


@pytest.fixture
def config_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Miner 1",
        unique_id=f"{IP}",
        data={
            CONF_IP: IP,
            CONF_TITLE: "Miner 1",
            CONF_MIN_POWER: 100,
            CONF_MAX_POWER: 5000,
        },
    )
    entry.add_to_hass(hass)
    return entry
