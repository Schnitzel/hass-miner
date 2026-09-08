"""Sensor platform for ASIC Miner integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from pyasic_rs.data import BoardData, MinerData, HashRateUnit

from .const import DOMAIN
from .coordinator import MinerCoordinator
from .entity import MinerEntity

UNIT_TH_S = "TH/s"
UNIT_J_TH = "J/TH"
UNIT_RPM = "RPM"


@dataclass(frozen=True, kw_only=True)
class MinerSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[MinerData], Any]
    available_fn: Callable[[MinerData], bool] = lambda _: True


# ── Top-level miner sensors ────────────────────────────────────────────────

MINER_SENSORS: tuple[MinerSensorEntityDescription, ...] = (
    MinerSensorEntityDescription(
        key="hashrate",
        name="Hashrate",
        icon="mdi:pickaxe",
        native_unit_of_measurement=UNIT_TH_S,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: (
            round(d.hashrate.into_unit(HashRateUnit.TH).value, 4)
            if d.hashrate
            else None
        ),
        available_fn=lambda d: d.hashrate is not None,
    ),
    MinerSensorEntityDescription(
        key="expected_hashrate",
        name="Expected Hashrate",
        icon="mdi:pickaxe",
        native_unit_of_measurement=UNIT_TH_S,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: (
            round(d.expected_hashrate.into_unit(HashRateUnit.TH).value, 4)
            if d.expected_hashrate
            else None
        ),
        available_fn=lambda d: d.expected_hashrate is not None,
    ),
    MinerSensorEntityDescription(
        key="average_temperature",
        name="Average Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.average_temperature,
        available_fn=lambda d: d.average_temperature is not None,
    ),
    MinerSensorEntityDescription(
        key="fluid_temperature",
        name="Fluid Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.fluid_temperature,
        available_fn=lambda d: d.fluid_temperature is not None,
    ),
    MinerSensorEntityDescription(
        key="wattage",
        name="Power Consumption",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: d.wattage,
        available_fn=lambda d: d.wattage is not None,
    ),
    MinerSensorEntityDescription(
        key="efficiency",
        name="Efficiency",
        icon="mdi:gauge",
        native_unit_of_measurement=UNIT_J_TH,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: d.efficiency,
        available_fn=lambda d: d.efficiency is not None,
    ),
    MinerSensorEntityDescription(
        key="uptime",
        name="Uptime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        value_fn=lambda d: int(d.uptime.total_seconds()) if d.uptime else None,
        available_fn=lambda d: d.uptime is not None,
    ),
    MinerSensorEntityDescription(
        key="total_chips",
        name="Total Active Chips",
        icon="mdi:chip",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.total_chips,
        available_fn=lambda d: d.total_chips is not None,
    ),
    MinerSensorEntityDescription(
        key="pool_accepted_shares",
        name="Pool Accepted Shares",
        icon="mdi:check",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _primary_pool_accepted(d),
        available_fn=lambda d: _primary_pool_accepted(d) is not None,
    ),
    MinerSensorEntityDescription(
        key="pool_rejected_shares",
        name="Pool Rejected Shares",
        icon="mdi:close",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _primary_pool_rejected(d),
        available_fn=lambda d: _primary_pool_rejected(d) is not None,
    ),
    MinerSensorEntityDescription(
        key="pool_url",
        name="Active Pool",
        icon="mdi:swim",
        value_fn=lambda d: _primary_pool_url(d),
        available_fn=lambda d: _primary_pool_url(d) is not None,
    ),
)


def _primary_pool(data: MinerData):
    """Return the first active pool across all pool groups, or the very first pool."""
    for group in data.pools:
        for pool in group.pools:
            if pool.active:
                return pool
    # Fall back to first pool if none are marked active
    for group in data.pools:
        if group.pools:
            return group.pools[0]
    return None


def _primary_pool_accepted(data: MinerData) -> int | None:
    pool = _primary_pool(data)
    return pool.accepted_shares if pool else None


def _primary_pool_rejected(data: MinerData) -> int | None:
    pool = _primary_pool(data)
    return pool.rejected_shares if pool else None


def _primary_pool_url(data: MinerData) -> str | None:
    pool = _primary_pool(data)
    return pool.url if pool else None


# ── Per-board sensor factories ──────────────────────────────────────────────


def _board_sensors(position: int) -> list[MinerSensorEntityDescription]:
    n = position
    return [
        MinerSensorEntityDescription(
            key=f"board_{n}_hashrate",
            name=f"Board {n} Hashrate",
            icon="mdi:pickaxe",
            native_unit_of_measurement=UNIT_TH_S,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=2,
            value_fn=lambda d, _n=n: _board_value(
                d,
                _n,
                lambda b: (
                    round(b.hashrate.into_unit(HashRateUnit.TH).value, 4)
                    if b.hashrate
                    else None
                ),
            ),
            available_fn=lambda d, _n=n: (
                _board_value(d, _n, lambda b: b.hashrate) is not None
            ),
        ),
        MinerSensorEntityDescription(
            key=f"board_{n}_board_temperature",
            name=f"Board {n} Temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            value_fn=lambda d, _n=n: _board_value(d, _n, lambda b: b.board_temperature),
            available_fn=lambda d, _n=n: (
                _board_value(d, _n, lambda b: b.board_temperature) is not None
            ),
        ),
        MinerSensorEntityDescription(
            key=f"board_{n}_intake_temperature",
            name=f"Board {n} Intake Temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            value_fn=lambda d, _n=n: _board_value(
                d, _n, lambda b: b.intake_temperature
            ),
            available_fn=lambda d, _n=n: (
                _board_value(d, _n, lambda b: b.intake_temperature) is not None
            ),
        ),
        MinerSensorEntityDescription(
            key=f"board_{n}_outlet_temperature",
            name=f"Board {n} Outlet Temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            value_fn=lambda d, _n=n: _board_value(
                d, _n, lambda b: b.outlet_temperature
            ),
            available_fn=lambda d, _n=n: (
                _board_value(d, _n, lambda b: b.outlet_temperature) is not None
            ),
        ),
        MinerSensorEntityDescription(
            key=f"board_{n}_working_chips",
            name=f"Board {n} Working Chips",
            icon="mdi:chip",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d, _n=n: _board_value(d, _n, lambda b: b.working_chips),
            available_fn=lambda d, _n=n: (
                _board_value(d, _n, lambda b: b.working_chips) is not None
            ),
        ),
        MinerSensorEntityDescription(
            key=f"board_{n}_frequency",
            name=f"Board {n} Frequency",
            native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
            device_class=SensorDeviceClass.FREQUENCY,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            value_fn=lambda d, _n=n: _board_value(d, _n, lambda b: b.frequency),
            available_fn=lambda d, _n=n: (
                _board_value(d, _n, lambda b: b.frequency) is not None
            ),
        ),
        MinerSensorEntityDescription(
            key=f"board_{n}_voltage",
            name=f"Board {n} Voltage",
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            device_class=SensorDeviceClass.VOLTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=2,
            value_fn=lambda d, _n=n: _board_value(d, _n, lambda b: b.voltage),
            available_fn=lambda d, _n=n: (
                _board_value(d, _n, lambda b: b.voltage) is not None
            ),
        ),
    ]


def _board_value(
    data: MinerData, position: int, getter: Callable[[BoardData], Any]
) -> Any:
    for board in data.hashboards:
        if board.position == position:
            return getter(board)
    return None


# ── Per-fan sensor factories ────────────────────────────────────────────────


def _fan_sensor(position: int, psu: bool = False) -> MinerSensorEntityDescription:
    prefix = "PSU Fan" if psu else "Fan"
    key_prefix = "psu_fan" if psu else "fan"
    return MinerSensorEntityDescription(
        key=f"{key_prefix}_{position}_rpm",
        name=f"{prefix} {position} RPM",
        icon="mdi:fan",
        native_unit_of_measurement=UNIT_RPM,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d, _p=position, _psu=psu: _fan_rpm(d, _p, _psu),
        available_fn=lambda d, _p=position, _psu=psu: _fan_rpm(d, _p, _psu) is not None,
    )


def _fan_rpm(data: MinerData, position: int, psu: bool) -> float | None:
    fans = data.psu_fans if psu else data.fans
    for fan in fans:
        if fan.position == position:
            return fan.rpm
    return None


# ── Entity class ────────────────────────────────────────────────────────────


class MinerSensorEntity(MinerEntity, SensorEntity):
    entity_description: MinerSensorEntityDescription

    def __init__(
        self,
        coordinator: MinerCoordinator,
        description: MinerSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._device_unique_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success or self.coordinator.data is None:
            return False
        return self.entity_description.available_fn(self.coordinator.data)


# ── Platform setup ──────────────────────────────────────────────────────────


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MinerCoordinator = hass.data[DOMAIN][entry.entry_id]

    descriptions: list[MinerSensorEntityDescription] = list(MINER_SENSORS)

    # Enumerate per-board / per-fan entities from the coordinator helpers (live
    # data first, then the cached profile). This way entities are still created
    # from the cached profile when ``data`` is None (miner offline at startup);
    # value_fns look the board/fan up by position at value time as before.
    for position in coordinator.board_positions:
        descriptions.extend(_board_sensors(position))

    # Add fan sensors
    for position in coordinator.fan_positions:
        descriptions.append(_fan_sensor(position, psu=False))

    # Add PSU fan sensors
    for position in coordinator.psu_fan_positions:
        descriptions.append(_fan_sensor(position, psu=True))

    async_add_entities(MinerSensorEntity(coordinator, desc) for desc in descriptions)
