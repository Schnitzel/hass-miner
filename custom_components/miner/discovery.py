"""Network discovery for ASIC Miner."""

from __future__ import annotations

import ipaddress
import logging

from homeassistant import config_entries
from homeassistant.components.network import async_get_adapters
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from pyasic_rs import MinerFactory

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
DISCOVERY_CONCURRENCY = 256


async def async_default_subnet(hass: HomeAssistant) -> str:
    """Return the IPv4 subnet of Home Assistant's default network adapter."""
    try:
        adapters = await async_get_adapters(hass)
        for adapter in adapters:
            if not adapter.get("default") or not adapter.get("ipv4"):
                continue
            ip_info = adapter["ipv4"][0]
            network = ipaddress.IPv4Network(
                f"{ip_info['address']}/{ip_info['network_prefix']}", strict=False
            )
            return str(network)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Could not determine the default network: %s", err)
    return "192.168.1.0/24"


async def async_scan_subnet(subnet: str) -> dict[str, str]:
    """Scan a subnet and return supported miner IPs and display names."""
    discovered: dict[str, str] = {}
    factory = MinerFactory.from_subnet(subnet).with_concurrent_limit(
        DISCOVERY_CONCURRENCY
    )
    async for ip, miner in factory.scan_stream_with_ip():
        if miner is not None:
            discovered[str(ip)] = f"{miner.make} {miner.model} ({ip})"
    return discovered


async def async_discover_miners(hass: HomeAssistant) -> None:
    """Scan the default subnet and start flows for unconfigured miners."""
    subnet = await async_default_subnet(hass)
    _LOGGER.debug("Scanning %s for ASIC miners", subnet)
    try:
        discovered = await async_scan_subnet(subnet)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Automatic ASIC miner discovery failed on %s: %s", subnet, err)
        return

    _LOGGER.debug("Found %d supported ASIC miner(s) on %s", len(discovered), subnet)
    configured_hosts = {
        entry.data.get(CONF_HOST) for entry in hass.config_entries.async_entries(DOMAIN)
    }
    for host, title in discovered.items():
        if host in configured_hosts:
            _LOGGER.debug("Skipping configured ASIC miner at %s", host)
            continue
        _LOGGER.debug("Starting discovery flow for %s", title)
        await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
            data={CONF_HOST: host, "title": title},
        )
