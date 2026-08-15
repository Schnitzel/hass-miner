"""Coordinator: MAC pinning, offline handling, no duplicate devices (#593, #538)."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.miner.const import CONF_MAC, DOMAIN

from .conftest import MAC, FakeMinerData, make_fake_miner


async def _setup(hass, config_entry):
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def _tick(hass, seconds=11):
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


def _entity_ids(hass, config_entry):
    ent_reg = er.async_get(hass)
    return {
        e.entity_id
        for e in er.async_entries_for_config_entry(ent_reg, config_entry.entry_id)
    }


async def test_setup_pins_mac_and_creates_single_device(
    hass, config_entry, mock_get_miner
):
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.data[CONF_MAC] == MAC

    dev_reg = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(dev_reg, config_entry.entry_id)
    assert len(devices) == 1
    assert (DOMAIN, MAC) in devices[0].identifiers

    ent_reg = er.async_get(hass)
    uids = {
        e.unique_id
        for e in er.async_entries_for_config_entry(ent_reg, config_entry.entry_id)
    }
    assert f"{MAC}-hashrate" in uids
    assert not any(u.startswith("None-") for u in uids)


async def test_initial_setup_with_missing_mac_retries_instead_of_creating_none_entities(
    hass, config_entry
):
    """Booting miner answers with mac=None -> ConfigEntryNotReady, no entities (#593)."""
    booting = make_fake_miner(FakeMinerData(mac=None))
    with patch("pyasic.get_miner", new=AsyncMock(return_value=booting)):
        assert not await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert _entity_ids(hass, config_entry) == set()
    assert CONF_MAC not in config_entry.data


async def test_initial_setup_offline_miner_retries(hass, config_entry):
    """get_miner returns None at setup -> retry, never zeroed placeholder entities."""
    with patch("pyasic.get_miner", new=AsyncMock(return_value=None)):
        assert not await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert _entity_ids(hass, config_entry) == set()


async def test_missing_mac_after_setup_reuses_pinned_mac(
    hass, config_entry, fake_miner, mock_get_miner
):
    """After a hard reboot the miner briefly reports mac=None: keep the pinned MAC."""
    await _setup(hass, config_entry)
    before = _entity_ids(hass, config_entry)

    fake_miner.get_data = AsyncMock(
        return_value=FakeMinerData(mac=None, hashrate=12.0)
    )
    await _tick(hass)

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    assert coordinator.last_update_success
    assert coordinator.data["mac"] == MAC
    assert coordinator.data["miner_sensors"]["hashrate"] == 12.0

    # Reload while the miner still reports mac=None -> must not create a _2 set.
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    after = _entity_ids(hass, config_entry)
    assert after == before
    dev_reg = dr.async_get(hass)
    assert len(dr.async_entries_for_config_entry(dev_reg, config_entry.entry_id)) == 1
    assert not any(eid.endswith("_2") for eid in after)


async def test_offline_first_failure_zeroed_then_unavailable(
    hass, config_entry, mock_get_miner
):
    """#538 kept post-setup: 1st failure -> zeroed data with pinned MAC; 2nd -> unavailable."""
    await _setup(hass, config_entry)
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    mock_get_miner.return_value = None
    await _tick(hass)
    assert coordinator.last_update_success
    assert coordinator.data["miner_sensors"]["hashrate"] == 0
    assert coordinator.data["mac"] == MAC  # identity preserved while offline
    assert coordinator.data["power_limit_range"] == {"min": 100, "max": 5000}

    await _tick(hass)
    assert not coordinator.last_update_success
    # Entities keep the last (zeroed) state; upstream deliberately reports 0 rather
    # than unavailable so global totals stay correct (#538).
    assert hass.states.get("sensor.miner_1_hashrate").state == "0"


async def test_recovery_resets_failure_count(
    hass, config_entry, fake_miner, mock_get_miner
):
    await _setup(hass, config_entry)
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    mock_get_miner.return_value = None
    await _tick(hass)
    await _tick(hass)
    assert not coordinator.last_update_success

    mock_get_miner.return_value = fake_miner
    await _tick(hass)
    assert coordinator.last_update_success
    assert coordinator._failure_count == 0
    # one more single failure is tolerated again
    mock_get_miner.return_value = None
    await _tick(hass)
    assert coordinator.last_update_success


async def test_config_fetch_error_retries_without_config(
    hass, config_entry, fake_miner, mock_get_miner
):
    """VNish CONFIG bug path: first call raises mentioning config, retry succeeds."""
    fake_miner.get_data = AsyncMock(
        side_effect=[Exception("Failed to call config"), FakeMinerData()]
    )
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    assert fake_miner.get_data.await_count == 2
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    assert coordinator.data["mac"] == MAC


async def test_get_data_generic_error_at_setup_retries(
    hass, config_entry, fake_miner, mock_get_miner
):
    fake_miner.get_data = AsyncMock(side_effect=Exception("boom"))
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
