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
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from pyasic_rs.data import BoardData, HashRateUnit, MinerData

from .const import (
    CAT_BOARD_PERF,
    CAT_BOARD_TEMPS,
    CAT_FANS,
    CAT_MINER_SUMMARY,
    CAT_SAFETY,
    CONF_ONLY_AVAILABLE,
    CONF_SENSOR_CATEGORIES,
    DEFAULT_ONLY_AVAILABLE,
    DEFAULT_SENSOR_CATEGORIES,
    DOMAIN,
)
from .coordinator import MinerCoordinator
from .entity import MinerEntity, async_remove_stale_entities

UNIT_TH_S = "TH/s"
UNIT_J_TH = "J/TH"
UNIT_RPM = "RPM"

# Severities (lowercased) that count as an active safety alarm.
_PROBLEM_SEVERITIES = ("error", "warning")

# Icons for sensors that would otherwise fall back to HA's generic icon.
# device_class sensors (temperature/power/…) keep their nice default icon
# unless overridden here. Per-board/fan keys are matched by suffix below.
_ICONS: dict[str, str] = {
    "hashrate": "mdi:pickaxe",
    "expected_hashrate": "mdi:pickaxe",
    "efficiency": "mdi:gauge",
    "wattage": "mdi:flash",
    "uptime": "mdi:timer-outline",
    "total_chips": "mdi:chip",
    "pool_accepted_shares": "mdi:check",
    "pool_rejected_shares": "mdi:close",
    "pool_url": "mdi:swim",
    "fluid_temperature": "mdi:thermometer-water",
    "outlet_fluid_temperature": "mdi:thermometer-water",
    "safety_alarm_reason": "mdi:shield-alert",
}
_ICON_SUFFIXES: dict[str, str] = {
    "_hashrate": "mdi:pickaxe",
    "_working_chips": "mdi:chip",
    "_rpm": "mdi:fan",
}


def _icon_for(key: str) -> str | None:
    if key in _ICONS:
        return _ICONS[key]
    for suffix, icon in _ICON_SUFFIXES.items():
        if key.endswith(suffix):
            return icon
    return None


@dataclass(frozen=True, kw_only=True)
class MinerSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[MinerData], Any]
    available_fn: Callable[[MinerData], bool] = lambda _: True


# ── Defensive capability helpers (Schicht B / B1) ───────────────────────────
# These read fields that exist only on the fork wheel; on stock pyasic-rs==0.6.2
# they are absent and return None so the only_available None-gate (A4) decides.


def _cooling_is_hydro(data: MinerData) -> bool | None:
    """True/False if the lib reports a cooling type, else None (unknown)."""
    cooling = getattr(getattr(data, "device_info", None), "cooling", None)
    if cooling is None:
        return None  # unknown on this lib version -> let only_available decide
    return str(cooling).lower() in ("hydro", "water", "liquid")


def _reports_chip_temp(data: MinerData) -> bool | None:
    """Lib's reports_chip_temperature flag, or None if absent on this lib."""
    return getattr(getattr(data, "device_info", None), "reports_chip_temperature", None)


# ── shared data helpers ─────────────────────────────────────────────────────


def _primary_pool(data: MinerData):
    """Return the first active pool across all pool groups, or the very first pool."""
    for group in data.pools:
        for pool in group.pools:
            if pool.active:
                return pool
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


def _board_value(
    data: MinerData, position: int, getter: Callable[[BoardData], Any]
) -> Any:
    for board in data.hashboards:
        if board.position == position:
            return getter(board)
    return None


def _fan_rpm(data: MinerData, position: int, psu: bool) -> float | None:
    fans = data.psu_fans if psu else data.fans
    for fan in fans:
        if fan.position == position:
            return fan.rpm
    return None


def _max_temperature(data: MinerData) -> float | None:
    """Hottest temperature reported across boards plus miner-wide temps.

    Per-board chip temps (``inlet_chip_temperature``/``outlet_chip_temperature``)
    and the miner-level coolant outlet (``outlet_fluid_temperature``) are read
    defensively, since not every lib version / miner exposes them.
    """
    temps: list[float] = []
    for board in data.hashboards:
        for t in (
            board.board_temperature,
            getattr(board, "inlet_chip_temperature", None),
            getattr(board, "outlet_chip_temperature", None),
        ):
            if t is not None:
                temps.append(t)
    for t in (
        data.average_temperature,
        getattr(data, "fluid_temperature", None),
        getattr(data, "outlet_fluid_temperature", None),
    ):
        if t is not None:
            temps.append(t)
    return max(temps) if temps else None


# ── Safety helpers (Schicht B / B2) ─────────────────────────────────────────
# All lib-dependent reads are defensive: with no messages and no thermal limits
# on stock 0.6.2 these reduce to _has_problem -> False and _alarm_reason -> "OK".


def _problem_messages(data: MinerData) -> list[str]:
    """Texts of the miner's own Error/Warning messages (its self-assessment).

    Defensive about both the presence of ``data.messages`` and the message
    object's shape: severity via ``.severity``, text via ``.message``/``.text``.
    """
    out: list[str] = []
    messages = getattr(data, "messages", None) or []
    for message in messages:
        try:
            severity = str(getattr(message, "severity", "") or "").lower()
            if severity not in _PROBLEM_SEVERITIES:
                continue
            text = getattr(message, "message", None)
            if text is None:
                text = getattr(message, "text", None)
            text = str(text or "").strip()
            if text and severity:
                out.append(f"{severity}: {text}")
            elif text:
                out.append(text)
            elif severity:
                out.append(severity)
        except Exception:  # noqa: BLE001 - never let a sensor crash setup/update
            continue
    return out


def _has_problem(data: MinerData) -> bool:
    return bool(_problem_messages(data))


def _alarm_reason(data: MinerData) -> str:
    """Human-readable alarm reason, aligned to device messages and thermal limits.

    ``OK`` when the miner reports nothing actionable. Device-read limits
    (``min_startup_temperature`` / ``restart_temperature``) and live temperatures
    are read defensively, so on stock 0.6.2 (no messages, no limits) this is "OK".
    """
    reasons: list[str] = list(_problem_messages(data))

    hot = getattr(data, "restart_temperature", None)
    cold = getattr(data, "min_startup_temperature", None)
    maxtemp = _max_temperature(data)
    inlet = getattr(data, "fluid_temperature", None)

    if hot is not None and maxtemp is not None and maxtemp >= hot:
        reasons.append(f"too hot ({maxtemp:.0f} °C ≥ {hot:.0f} °C)")
    if cold is not None and inlet is not None and inlet < cold:
        reasons.append(
            f"inlet water too cold (mining won't start) "
            f"({inlet:.0f} °C < {cold:.0f} °C)"
        )

    if not reasons:
        return "OK"
    return "; ".join(reasons)


# ── Miner-Summary: miner-wide aggregates / statistics (CAT_MINER_SUMMARY) ────

MINER_SENSORS: tuple[MinerSensorEntityDescription, ...] = (
    MinerSensorEntityDescription(
        key="hashrate",
        name="Hashrate",
        native_unit_of_measurement=UNIT_TH_S,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: (
            round(d.hashrate.into_unit(HashRateUnit.TH).value, 4) if d.hashrate else None
        ),
        available_fn=lambda d: d.hashrate is not None,
    ),
    MinerSensorEntityDescription(
        key="expected_hashrate",
        name="Expected Hashrate",
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
        key="max_temperature",
        name="Max Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-alert",
        value_fn=_max_temperature,
        available_fn=lambda d: _max_temperature(d) is not None,
    ),
    # Coolant inlet — the miner-level fluid temperature (water inlet on hydro).
    MinerSensorEntityDescription(
        key="fluid_temperature",
        name="Coolant Inlet",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: getattr(d, "fluid_temperature", None),
        available_fn=lambda d: getattr(d, "fluid_temperature", None) is not None,
    ),
    # Coolant outlet — the miner-level exhaust/return fluid temperature. Only
    # present on water-cooled miners with the sensor; None (and thus dropped)
    # otherwise.
    MinerSensorEntityDescription(
        key="outlet_fluid_temperature",
        name="Coolant Outlet",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: getattr(d, "outlet_fluid_temperature", None),
        available_fn=lambda d: getattr(d, "outlet_fluid_temperature", None) is not None,
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
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.total_chips,
        available_fn=lambda d: d.total_chips is not None,
    ),
    MinerSensorEntityDescription(
        key="pool_accepted_shares",
        name="Pool Accepted Shares",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_primary_pool_accepted,
        available_fn=lambda d: _primary_pool_accepted(d) is not None,
    ),
    MinerSensorEntityDescription(
        key="pool_rejected_shares",
        name="Pool Rejected Shares",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_primary_pool_rejected,
        available_fn=lambda d: _primary_pool_rejected(d) is not None,
    ),
    MinerSensorEntityDescription(
        key="pool_url",
        name="Active Pool",
        value_fn=_primary_pool_url,
        available_fn=lambda d: _primary_pool_url(d) is not None,
    ),
)

# Members of Miner-Summary that only make sense on liquid-cooled miners. When the
# lib reports cooling we trust it; otherwise the only_available None-gate decides.
_SUMMARY_HYDRO_ONLY = ("fluid_temperature", "outlet_fluid_temperature")


# ── Safety / Diagnose (CAT_SAFETY) ──────────────────────────────────────────

# The safety alarm reason is now a dedicated coordinator-aware entity
# (``MinerSafetyReasonSensor``) so it can also surface the boot-timeout latch,
# rather than a data-only value_fn description.

# The device's OWN configured thermal limits, surfaced as diagnostics so the
# alarm's comparison values are visible. Schicht B: read defensively, so they
# only appear when the lib exposes them (dormant on stock 0.6.2).
SAFETY_LIMIT_SENSORS: tuple[MinerSensorEntityDescription, ...] = (
    MinerSensorEntityDescription(
        key="safety_cold_limit",
        name="Safety Cold Limit",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:thermometer-low",
        value_fn=lambda d: getattr(d, "min_startup_temperature", None),
        available_fn=lambda d: getattr(d, "min_startup_temperature", None) is not None,
    ),
    MinerSensorEntityDescription(
        key="safety_hot_limit",
        name="Safety Hot Limit",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:thermometer-high",
        value_fn=lambda d: getattr(d, "restart_temperature", None),
        available_fn=lambda d: getattr(d, "restart_temperature", None) is not None,
    ),
)


# ── Per-board sensor factories ──────────────────────────────────────────────


def _board_temp_sensors(n: int) -> list[MinerSensorEntityDescription]:
    """Per-board temperature sensors (CAT_BOARD_TEMPS).

    ``board_{n}_inlet_chip_temperature`` / ``board_{n}_outlet_chip_temperature``
    (B3) read the inlet-/outlet-side CHIP temps defensively; where the firmware
    doesn't report chip temps the value is None and only_available drops them.
    The PCB ``board_temperature`` sensor is always emitted.
    """
    return [
        MinerSensorEntityDescription(
            key=f"board_{n}_board_temperature",
            name=f"Board {n} Temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            value_fn=lambda d, _n=n: _board_value(d, _n, lambda b: b.board_temperature),
            available_fn=lambda d, _n=n: _board_value(
                d, _n, lambda b: b.board_temperature
            )
            is not None,
        ),
        MinerSensorEntityDescription(
            key=f"board_{n}_inlet_chip_temperature",
            name=f"Board {n} Chip Temp (inlet)",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            value_fn=lambda d, _n=n: _board_value(
                d, _n, lambda b: getattr(b, "inlet_chip_temperature", None)
            ),
            available_fn=lambda d, _n=n: _board_value(
                d, _n, lambda b: getattr(b, "inlet_chip_temperature", None)
            )
            is not None,
        ),
        MinerSensorEntityDescription(
            key=f"board_{n}_outlet_chip_temperature",
            name=f"Board {n} Chip Temp (outlet)",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            value_fn=lambda d, _n=n: _board_value(
                d, _n, lambda b: getattr(b, "outlet_chip_temperature", None)
            ),
            available_fn=lambda d, _n=n: _board_value(
                d, _n, lambda b: getattr(b, "outlet_chip_temperature", None)
            )
            is not None,
        ),
    ]


def _board_perf_sensors(n: int) -> list[MinerSensorEntityDescription]:
    """Per-board performance sensors (CAT_BOARD_PERF)."""
    return [
        MinerSensorEntityDescription(
            key=f"board_{n}_hashrate",
            name=f"Board {n} Hashrate",
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
            available_fn=lambda d, _n=n: _board_value(d, _n, lambda b: b.hashrate)
            is not None,
        ),
        MinerSensorEntityDescription(
            key=f"board_{n}_working_chips",
            name=f"Board {n} Working Chips",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d, _n=n: _board_value(d, _n, lambda b: b.working_chips),
            available_fn=lambda d, _n=n: _board_value(d, _n, lambda b: b.working_chips)
            is not None,
        ),
        MinerSensorEntityDescription(
            key=f"board_{n}_frequency",
            name=f"Board {n} Frequency",
            native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
            device_class=SensorDeviceClass.FREQUENCY,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            value_fn=lambda d, _n=n: _board_value(d, _n, lambda b: b.frequency),
            available_fn=lambda d, _n=n: _board_value(d, _n, lambda b: b.frequency)
            is not None,
        ),
        MinerSensorEntityDescription(
            key=f"board_{n}_voltage",
            name=f"Board {n} Voltage",
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            device_class=SensorDeviceClass.VOLTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=2,
            value_fn=lambda d, _n=n: _board_value(d, _n, lambda b: b.voltage),
            available_fn=lambda d, _n=n: _board_value(d, _n, lambda b: b.voltage)
            is not None,
        ),
    ]


def _fan_sensor(position: int, psu: bool = False) -> MinerSensorEntityDescription:
    prefix = "PSU Fan" if psu else "Fan"
    key_prefix = "psu_fan" if psu else "fan"
    return MinerSensorEntityDescription(
        key=f"{key_prefix}_{position}_rpm",
        name=f"{prefix} {position} RPM",
        native_unit_of_measurement=UNIT_RPM,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d, _p=position, _psu=psu: _fan_rpm(d, _p, _psu),
        available_fn=lambda d, _p=position, _psu=psu: _fan_rpm(d, _p, _psu) is not None,
    )


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
        if description.icon is None:
            icon = _icon_for(description.key)
            if icon is not None:
                self._attr_icon = icon

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


class MinerSafetyReasonSensor(MinerEntity, SensorEntity):
    """Coordinator-aware safety alarm reason.

    Unlike the data-only sensors this also surfaces the coordinator-level
    boot-timeout latch (which is not part of MinerData), so the reason text can
    explain a miner that never came up after power-on. Keeps the historic key
    ``safety_alarm_reason`` so the unique_id is unchanged from earlier alphas.
    """

    _attr_name = "Safety Alarm Reason"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:shield-alert"

    def __init__(self, coordinator: MinerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device_unique_id}_safety_alarm_reason"

    @property
    def native_value(self) -> str:
        coordinator = self.coordinator
        data = coordinator.data
        if coordinator.boot_failed:
            boot_msg = (
                f"miner did not come online within {coordinator.boot_timeout}s "
                "after power-on"
            )
            if data is not None:
                reason = _alarm_reason(data)
                if reason and reason != "OK":
                    return f"{boot_msg}; {reason}"
            return boot_msg
        if data is not None:
            reason = _alarm_reason(data)
            # VNish treats tuning as a normal state (no message → reason "OK"),
            # but surfacing it as info explains why hashrate is ramping/variable.
            if reason == "OK":
                state = (coordinator.vnish_state or "").lower()
                if state in ("tuning", "auto-tuning", "auto_tuning"):
                    return "tuning in progress"
            return reason
        # No data and not a boot failure: distinguish "powered off" from a plain
        # communication outage so the reason text is meaningful while offline.
        if coordinator.power_entity and not coordinator.power_on:
            return "powered off"
        return "unavailable"

    @property
    def available(self) -> bool:
        # Always meaningful while the entity exists (boot/offline reasons too).
        return True


# ── Platform setup ──────────────────────────────────────────────────────────


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MinerCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data

    categories = set(
        entry.options.get(CONF_SENSOR_CATEGORIES, DEFAULT_SENSOR_CATEGORIES)
    )
    only_available = entry.options.get(CONF_ONLY_AVAILABLE, DEFAULT_ONLY_AVAILABLE)

    # Capability gates (Schicht B / B1), defensive: True/False when the lib knows,
    # None on stock 0.6.2 / when offline so the only_available None-gate decides.
    is_hydro = _cooling_is_hydro(data) if data is not None else None
    reports_chip = _reports_chip_temp(data) if data is not None else None

    descriptions: list[MinerSensorEntityDescription] = []
    # The coordinator-backed safety-reason sensor is added separately (it is not
    # a value_fn description); track it here so stale-cleanup keeps it.
    extra_keys: set[str] = set()
    add_safety_reason = False

    # Miner-wide aggregates / statistics.
    if CAT_MINER_SUMMARY in categories:
        for d in MINER_SENSORS:
            # Hydro-only members: drop only when the lib positively says "not hydro".
            if d.key in _SUMMARY_HYDRO_ONLY and is_hydro is False:
                continue
            descriptions.append(d)

    # Safety / diagnose: the coordinator-aware alarm reason + device thermal limits.
    if CAT_SAFETY in categories:
        add_safety_reason = True
        extra_keys.add("safety_alarm_reason")
        descriptions.extend(SAFETY_LIMIT_SENSORS)

    # Per-board sensors, enumerated from the coordinator (live data when present,
    # else the cached profile) so they exist even when the miner is offline.
    if CAT_BOARD_TEMPS in categories or CAT_BOARD_PERF in categories:
        for n in coordinator.board_positions:
            if CAT_BOARD_TEMPS in categories:
                chip_keys = (
                    f"board_{n}_inlet_chip_temperature",
                    f"board_{n}_outlet_chip_temperature",
                )
                for d in _board_temp_sensors(n):
                    # Chip temps: drop only when the lib positively says they
                    # aren't reported.
                    if d.key in chip_keys and reports_chip is False:
                        continue
                    descriptions.append(d)
            if CAT_BOARD_PERF in categories:
                descriptions.extend(_board_perf_sensors(n))

    # Fan RPM sensors, enumerated from the coordinator (live data or cache).
    if CAT_FANS in categories:
        for pos in coordinator.fan_positions:
            descriptions.append(_fan_sensor(pos, psu=False))
        for pos in coordinator.psu_fan_positions:
            descriptions.append(_fan_sensor(pos, psu=True))

    # only_available gate (A4): drop descriptions whose value is unavailable now.
    # When offline (data is None) we cannot evaluate availability — create
    # everything from the profile; the entities are unavailable anyway until a
    # poll succeeds, and a later reload re-applies the filter.
    if only_available and data is not None:
        descriptions = [d for d in descriptions if d.available_fn(data)]

    # Clean up entities of any category/sensor we are no longer producing
    # (same unique-id scheme as MinerEntity). device_uid prefers MAC (live or
    # cached) so we never wipe entities just because the miner is momentarily
    # offline.
    mac = coordinator.device_mac
    device_uid = mac.replace(":", "").lower() if mac else coordinator.ip
    keep = {f"{device_uid}_{d.key}" for d in descriptions} | {
        f"{device_uid}_{k}" for k in extra_keys
    }
    async_remove_stale_entities(hass, entry, "sensor", keep)

    entities: list[SensorEntity] = [
        MinerSensorEntity(coordinator, desc) for desc in descriptions
    ]
    if add_safety_reason:
        entities.append(MinerSafetyReasonSensor(coordinator))
    async_add_entities(entities)
