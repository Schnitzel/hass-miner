"""Power limit number entity error handling (#564)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError

ENTITY = "number.miner_1_power_limit"


async def _setup(hass, config_entry):
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def _set(hass, value):
    await hass.services.async_call(
        "number", "set_value", {"entity_id": ENTITY, "value": value}, blocking=True
    )


async def test_set_power_limit_ok(hass, config_entry, fake_miner, mock_get_miner):
    await _setup(hass, config_entry)
    assert hass.states.get(ENTITY) is not None
    await _set(hass, 2500)
    fake_miner.set_power_limit.assert_awaited_once_with(2500)
    assert float(hass.states.get(ENTITY).state) == 2500


async def test_set_power_limit_no_presets_gives_clear_error(
    hass, config_entry, fake_miner, mock_get_miner
):
    """Pyasic ValueError('max() iterable argument is empty') -> friendly error."""
    await _setup(hass, config_entry)
    fake_miner.set_power_limit = AsyncMock(
        side_effect=ValueError("max() iterable argument is empty")
    )
    with pytest.raises(HomeAssistantError, match="no tunable power presets"):
        await _set(hass, 2500)


async def test_set_power_limit_rejected(hass, config_entry, fake_miner, mock_get_miner):
    await _setup(hass, config_entry)
    fake_miner.set_power_limit = AsyncMock(return_value=False)
    with pytest.raises(HomeAssistantError, match="rejected power limit 2500"):
        await _set(hass, 2500)


async def test_set_power_limit_unsupported(
    hass, config_entry, fake_miner, mock_get_miner
):
    await _setup(hass, config_entry)
    fake_miner.supports_autotuning = False
    with pytest.raises(HomeAssistantError, match="Tuning not supported"):
        await _set(hass, 2500)
