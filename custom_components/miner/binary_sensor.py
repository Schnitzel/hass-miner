"""Binary sensor platform for ASIC Miner integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from pyasic_rs.data import MinerData

from .const import (
    CAT_MINER_SUMMARY,
    CAT_SAFETY,
    CONF_SENSOR_CATEGORIES,
    DEFAULT_SENSOR_CATEGORIES,
    DOMAIN,
)
from .coordinator import MinerCoordinator
from .entity import MinerEntity, async_remove_stale_entities
from .sensor import _has_problem


@dataclass(frozen=True, kw_only=True)
class MinerBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[MinerData], bool | None]
    available_fn: Callable[[MinerData], bool] = lambda _: True


# Miner-wide status flags (CAT_MINER_SUMMARY).
BINARY_SENSORS: tuple[MinerBinarySensorDescription, ...] = (
    MinerBinarySensorDescription(
        key="is_mining",
        name="Mining",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda d: d.is_mining,
    ),
    MinerBinarySensorDescription(
        key="light_flashing",
        name="Fault Light",
        value_fn=lambda d: d.light_flashing,
        available_fn=lambda d: d.light_flashing is not None,
    ),
)

# Safety (CAT_SAFETY): on when the miner reports its own Error/Warning state.
# Defensive (B2): with no messages on stock 0.6.2, _has_problem -> False.
SAFETY_BINARY_SENSORS: tuple[MinerBinarySensorDescription, ...] = (
    MinerBinarySensorDescription(
        key="safety_problem",
        name="Safety Problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_has_problem,
    ),
)


class MinerBootTimeoutBinarySensor(MinerEntity, BinarySensorEntity):
    """Coordinator-backed boot-timeout alarm (not MinerData-backed).

    Only created when a power_entity is configured AND CAT_SAFETY is enabled.
    Latches ON when the miner fails to come up within boot_timeout after a
    power-on transition.
    """

    _attr_name = "Boot Timeout"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:timer-alert"

    def __init__(self, coordinator: MinerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_unique_id}_boot_timeout"

    @property
    def is_on(self) -> bool:
        return self.coordinator.boot_failed

    @property
    def available(self) -> bool:
        # The alarm itself is always meaningful while the entity exists.
        return True


class MinerBinarySensorEntity(MinerEntity, BinarySensorEntity):
    entity_description: MinerBinarySensorDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        description: MinerBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._device_unique_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success or self.coordinator.data is None:
            return False
        return self.entity_description.available_fn(self.coordinator.data)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MinerCoordinator = hass.data[DOMAIN][entry.entry_id]

    categories = set(
        entry.options.get(CONF_SENSOR_CATEGORIES, DEFAULT_SENSOR_CATEGORIES)
    )

    descriptions: list[MinerBinarySensorDescription] = []
    if CAT_MINER_SUMMARY in categories:
        descriptions.extend(BINARY_SENSORS)
    if CAT_SAFETY in categories:
        descriptions.extend(SAFETY_BINARY_SENSORS)

    # Boot-timeout alarm: coordinator-backed, only when power-aware polling is
    # configured and the safety category is enabled.
    add_boot_timeout = CAT_SAFETY in categories and coordinator.power_entity

    mac = coordinator.device_mac
    device_uid = mac.replace(":", "").lower() if mac else coordinator.ip
    keep = {f"{device_uid}_{d.key}" for d in descriptions}
    if add_boot_timeout:
        keep.add(f"{device_uid}_boot_timeout")
    async_remove_stale_entities(hass, entry, "binary_sensor", keep)

    entities: list[BinarySensorEntity] = [
        MinerBinarySensorEntity(coordinator, desc) for desc in descriptions
    ]
    if add_boot_timeout:
        entities.append(MinerBootTimeoutBinarySensor(coordinator))

    async_add_entities(entities)
