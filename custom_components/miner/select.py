"""Select platform for ASIC Miner integration.

BETA SOLUTION: VNish autotune-preset control. asic-rs is read-only for VNish
presets, so this entity drives the VNish REST API directly (see vnish.py).
Replace with the native miner method once asic-rs supports VNish writes.
"""

from __future__ import annotations

import re

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import vnish
from .const import DOMAIN
from .coordinator import MinerCoordinator
from .entity import MinerEntity


class VnishPresetSelect(MinerEntity, SelectEntity):
    """[BETA] Select a VNish autotune preset by name."""

    _attr_name = "VNish Preset"
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator: MinerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_unique_id}_vnish_preset"

    def _label_for(self, name: str | None) -> str | None:
        if name is None:
            return None
        return self.coordinator.vnish_preset_labels.get(name, name)

    def _name_for(self, label: str) -> str:
        """Map a displayed label back to the canonical preset name VNish expects.

        Prefer the exact label→name map; fall back to pulling the leading watt
        number straight out of the label (VNish preset names are the bare number,
        e.g. ``3495 W ~ 132 TH`` → ``3495``) so selection still resolves even if
        the label map is stale or empty (e.g. offline). A label with no number
        (``Disabled``) is returned lowercased to match the ``disabled`` preset.
        """
        for name, lbl in self.coordinator.vnish_preset_labels.items():
            if lbl == label:
                return name
        m = re.match(r"\s*(\d+)", label)
        if m:
            return m.group(1)
        return label.strip().lower()

    @property
    def options(self) -> list[str]:
        names = self.coordinator.vnish_presets or list(vnish.FALLBACK_PRESETS)
        return [self._label_for(n) for n in names]

    @property
    def current_option(self) -> str | None:
        return self._label_for(self.coordinator.vnish_preset)

    async def async_select_option(self, option: str) -> None:
        # ``option`` is the display label (e.g. "3495 W ~ 132 TH"); the VNish API
        # needs the bare preset name ("3495").
        name = self._name_for(option)
        session = async_get_clientsession(self.hass)
        ok, msg = await vnish.apply_preset(
            session, self.coordinator.ip, self.coordinator.password, name
        )
        if ok:
            self.coordinator.vnish_preset = name
            self.async_write_ha_state()
        else:
            raise RuntimeError(f"VNish preset '{name}' failed: {msg}")
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MinerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[MinerEntity] = []

    # VNish detection comes from the live connection; when offline-at-startup we
    # fall back to the cached profile so the shim entities still appear.
    is_vnish = coordinator.is_vnish or bool(
        coordinator.profile and coordinator.profile.get("is_vnish")
    )
    if is_vnish:
        entities.append(VnishPresetSelect(coordinator))

    async_add_entities(entities)
