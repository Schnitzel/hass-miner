"""Provides device actions for Miner."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.components.device_automation import async_validate_entity_schema
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.const import CONF_DOMAIN
from homeassistant.const import CONF_TYPE
from homeassistant.core import Context
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .const import SERVICE_REBOOT
from .const import SERVICE_RESTART_BACKEND
from .const import SERVICE_SET_WORK_MODE

_LOGGER = logging.getLogger(__name__)

ACTION_TYPES = {"reboot", "restart_backend", "set_work_mode"}

ACTION_SCHEMA = cv.DEVICE_ACTION_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(ACTION_TYPES),
        vol.Required(CONF_DOMAIN): DOMAIN,
        # Device actions operate on device registry IDs, not entity IDs
        vol.Required(CONF_DEVICE_ID): str,
        # For set_work_mode, accept a mode; default aligns with services.yaml
        vol.Optional("mode", default="high"): vol.In(["low", "normal", "high"]),
    }
)


async def async_validate_action_config(
    hass: HomeAssistant, config: ConfigType
) -> ConfigType:
    """Validate config."""
    return async_validate_entity_schema(hass, config, ACTION_SCHEMA)


async def async_get_actions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List device actions for Miner devices."""
    actions = []

    base_action = {
        CONF_DEVICE_ID: device_id,
        CONF_DOMAIN: DOMAIN,
    }
    for action_type in ACTION_TYPES:
        try:
            actions.append(
                {
                    **base_action,
                    CONF_TYPE: action_type,
                }
            )
        except AttributeError:
            _LOGGER.error(
                "Failed to add device command for miner: Unable to access entry data."
            )

    return actions


async def async_call_action_from_config(
    hass: HomeAssistant, config: dict, variables: dict, context: Context | None
) -> None:
    """Execute a device action."""
    service = None
    service_data = {CONF_DEVICE_ID: [config[CONF_DEVICE_ID]]}

    if config[CONF_TYPE] == "reboot":
        service = SERVICE_REBOOT
    elif config[CONF_TYPE] == "restart_backend":
        service = SERVICE_RESTART_BACKEND
    elif config[CONF_TYPE] == "set_work_mode":
        service = SERVICE_SET_WORK_MODE
        service_data["mode"] = config.get("mode", "high")

    if service is None:
        _LOGGER.error(f"Failed to call the service {config[CONF_TYPE]} for miner.")
        return
    await hass.services.async_call(
        DOMAIN, service, service_data, blocking=True, context=context
    )
