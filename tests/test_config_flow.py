"""Config flow: user flow and reconfigure (#440)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.miner.const import (
    CONF_IP,
    CONF_MAC,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_TITLE,
    DOMAIN,
)

from .conftest import IP, MAC, FakeMinerData, make_fake_miner


async def test_user_flow_creates_entry(hass, mock_get_miner):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_IP: IP, CONF_MIN_POWER: 100, CONF_MAX_POWER: 5000}
    )
    # fake miner has no api/web/ssh -> login step skipped -> title step
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "title"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TITLE: "My Miner"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "My Miner"
    assert result["data"][CONF_IP] == IP


async def test_user_flow_unreachable_ip_shows_error(hass):
    with patch("pyasic.get_miner", new=AsyncMock(return_value=None)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_IP: "10.0.0.1"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]


async def test_reconfigure_changes_ip(hass, config_entry, mock_get_miner):
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.data[CONF_MAC] == MAC

    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_IP: "192.168.1.99", CONF_MIN_POWER: 200, CONF_MAX_POWER: 4000},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_IP] == "192.168.1.99"
    assert config_entry.data[CONF_MIN_POWER] == 200
    assert config_entry.data[CONF_MAX_POWER] == 4000
    assert config_entry.data[CONF_MAC] == MAC  # identity kept


async def test_reconfigure_rejects_different_miner(hass, config_entry, mock_get_miner):
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    other = make_fake_miner(FakeMinerData(mac="11:22:33:44:55:66"))
    with patch("pyasic.get_miner", new=AsyncMock(return_value=other)):
        result = await config_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_IP: "192.168.1.77"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "different_miner"}
    assert config_entry.data[CONF_IP] == IP  # unchanged


async def test_reconfigure_unreachable_ip_shows_error(
    hass, config_entry, mock_get_miner
):
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    with patch("pyasic.get_miner", new=AsyncMock(return_value=None)):
        result = await config_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_IP: "192.168.1.77"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]
