"""VNish firmware REST client — BETA SOLUTION.

This is an interim, VNish-specific control path. pyasic-rs (asic-rs) currently
exposes the VNish backend as read-only for power/presets (set_power_limit is an
unimplemented stub), so this module talks to the VNish firmware REST API
directly to provide the named-preset and throttle controls.

It is intentionally self-contained and clearly marked BETA: once asic-rs gains
native VNish write support, the select/number entities should switch to the
miner object's methods and this module can be dropped.

Endpoints (base = http://{ip}/api/v1):
  GET  /info               -> firmware identity (fw_name == "Vnish")
  POST /unlock {pw}        -> {"token": ...}
  GET  /settings           -> miner.overclock (auth)
  GET  /autotune/presets   -> autotune preset list (auth)
  POST /settings           -> apply overclock (auth)
  GET  /summary            -> miner.miner_status.throttled (unauth)
  POST /mining/throttle    -> {"percent": N} (auth)
  POST /mining/restart     -> restart mining (auth)
"""

from __future__ import annotations

import contextlib
import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=15)

# Non-modded-PSU presets, used as a fallback when the live preset list cannot
# be fetched (e.g. no password configured). Higher presets (5725..7150) need a
# modded PSU and are intentionally omitted.
FALLBACK_PRESETS = [
    "disabled", "3495", "3635", "3865", "4200", "4250",
    "4400", "4650", "4855", "5150", "5415", "5560",
]

THROTTLE_MIN = 20
THROTTLE_MAX = 100


def _base(ip: str) -> str:
    return f"http://{ip}/api/v1"


async def detect_vnish(session: aiohttp.ClientSession, ip: str) -> bool:
    """Return True if the miner at ip runs VNish firmware."""
    try:
        async with session.get(f"{_base(ip)}/info", timeout=_TIMEOUT) as resp:
            if resp.status != 200:
                return False
            info = await resp.json()
    except Exception:  # noqa: BLE001
        return False
    return str(info.get("fw_name", "")).lower() == "vnish"


async def _unlock(session: aiohttp.ClientSession, ip: str, pw: str | None) -> str | None:
    """Obtain an unlock token, or None if it fails (miner off / wrong pw)."""
    try:
        async with session.post(
            f"{_base(ip)}/unlock", json={"pw": pw or ""}, timeout=_TIMEOUT
        ) as resp:
            body = await resp.json()
    except Exception:  # noqa: BLE001
        return None
    return body.get("token")


async def _fetch_summary_miner(
    session: aiohttp.ClientSession, ip: str
) -> dict | None:
    """GET /summary and return its ``miner`` object (unauth). None on failure."""
    try:
        async with session.get(f"{_base(ip)}/summary", timeout=_TIMEOUT) as resp:
            return (await resp.json()).get("miner", {}) or {}
    except Exception:  # noqa: BLE001
        return None


def _parse_throttle(miner: dict) -> int | None:
    val = miner.get("miner_status", {}).get("throttled", miner.get("throttled"))
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


async def fetch_status(
    session: aiohttp.ClientSession, ip: str
) -> tuple[int | None, str | None]:
    """Read ``(throttle_percent, miner_state)`` from /summary in one call (unauth).

    ``throttle`` is 100 when unthrottled. ``miner_state`` is VNish's own verdict
    (e.g. ``mining`` / ``tuning`` / ``initializing`` / ``stopped``), used to
    surface a friendly "tuning in progress" note without a second request.
    """
    miner = await _fetch_summary_miner(session, ip)
    if miner is None:
        return (None, None)
    state = miner.get("miner_status", {}).get("miner_state")
    return (_parse_throttle(miner), str(state) if state is not None else None)


async def fetch_throttle(session: aiohttp.ClientSession, ip: str) -> int | None:
    """Read the current throttle percent (unauth). 100 == unthrottled."""
    throttle, _ = await fetch_status(session, ip)
    return throttle


def preset_label(name: str, pretty: str | None, status: str | None) -> str:
    """Human-readable Select label for a preset option.

    Tuned presets show the firmware's ``pretty`` string with its hashrate
    estimate (``3495 watt ~ 132 TH`` → ``3495 W ~ 132 TH``); un-tuned numeric
    presets are marked (``5725 W (untuned)``) so it is clear that selecting one
    kicks off a tuning cycle first. Non-numeric presets (e.g. ``disabled``) keep
    their ``pretty``/name as-is.
    """
    raw = str(name).strip()
    if not raw.lstrip("-").isdigit():
        return (pretty or raw).strip() or raw
    if (status or "").lower() == "tuned" and pretty:
        return " ".join(pretty.replace("watt", "W").split())
    return f"{raw} W (untuned)"


async def fetch_presets(
    session: aiohttp.ClientSession, ip: str, pw: str | None
) -> list[dict]:
    """Read the available autotune presets (auth).

    Returns a list of ``{"name", "pretty", "status"}`` dicts (order preserved),
    or ``[]`` on failure. The name is the canonical value VNish expects; pretty
    and status drive the Select label via :func:`preset_label`.
    """
    token = await _unlock(session, ip, pw)
    if not token:
        return []
    try:
        async with session.get(
            f"{_base(ip)}/autotune/presets",
            headers={"Authorization": token},
            timeout=_TIMEOUT,
        ) as resp:
            presets = await resp.json()
    except Exception:  # noqa: BLE001
        return []
    plist = presets if isinstance(presets, list) else presets.get("presets", [])
    return [
        {
            "name": p["name"],
            "pretty": p.get("pretty"),
            "status": p.get("status"),
        }
        for p in plist
        if isinstance(p, dict) and p.get("name")
    ]


async def fetch_current_preset(
    session: aiohttp.ClientSession, ip: str, pw: str | None
) -> str | None:
    """Read the current overclock preset name (auth)."""
    token = await _unlock(session, ip, pw)
    if not token:
        return None
    try:
        async with session.get(
            f"{_base(ip)}/settings",
            headers={"Authorization": token},
            timeout=_TIMEOUT,
        ) as resp:
            s = await resp.json()
    except Exception:  # noqa: BLE001
        return None
    return s.get("miner", {}).get("overclock", {}).get("preset")


async def apply_preset(
    session: aiohttp.ClientSession, ip: str, pw: str | None, preset: str
) -> tuple[bool, str]:
    """Apply an autotune preset by name.

    Ports the proven shim logic: unlock -> GET /settings + /autotune/presets ->
    POST /settings with the preset + its tune_settings -> restart mining if
    VNish requires it.
    """
    token = await _unlock(session, ip, pw)
    if not token:
        return (False, "unlock failed (miner off / wrong pw?)")
    h = {"Authorization": token}
    try:
        async with session.get(f"{_base(ip)}/settings", headers=h, timeout=_TIMEOUT) as r:
            settings = await r.json()
        async with session.get(
            f"{_base(ip)}/autotune/presets", headers=h, timeout=_TIMEOUT
        ) as r:
            presets = await r.json()
    except Exception as err:  # noqa: BLE001
        return (False, f"read settings/presets failed: {err}")

    plist = presets if isinstance(presets, list) else presets.get("presets", [])
    tune = None
    for p in plist:
        if isinstance(p, dict) and p.get("name") == preset:
            tune = p.get("tune_settings")
            break

    oc = settings.get("miner", {}).get("overclock", {})
    new_oc = dict(oc)
    new_oc["preset"] = preset
    if tune:
        tf, tv = tune.get("freq"), tune.get("volt")
        if tf is not None or tv is not None:
            g = dict(new_oc.get("globals", {}))
            if tf is not None:
                g["freq"] = tf
            if tv is not None:
                g["volt"] = tv // 10  # tune_settings volt is 10x globals (mV vs deciV)
            new_oc["globals"] = g
        tch, cch = tune.get("chains", []), new_oc.get("chains", [])
        if tch and cch:
            nc = []
            for i, ch in enumerate(cch):
                ch = dict(ch)
                if i < len(tch):
                    ch["freq"] = tch[i].get("freq", ch.get("freq"))
                    ch["chips"] = tch[i].get("chips", ch.get("chips"))
                nc.append(ch)
            new_oc["chains"] = nc

    try:
        async with session.post(
            f"{_base(ip)}/settings",
            json={"miner": {"overclock": new_oc}},
            headers=h,
            timeout=_TIMEOUT,
        ) as r:
            ok = r.status == 200
            body = {}
            with contextlib.suppress(Exception):
                body = await r.json()
        if ok and body.get("restart_required"):
            async with session.post(
                f"{_base(ip)}/mining/restart", headers=h, timeout=_TIMEOUT
            ):
                pass
    except Exception as err:  # noqa: BLE001
        return (False, f"apply failed: {err}")
    return (ok, f"HTTP {'200' if ok else 'error'} restart={body.get('restart_required')}")


async def set_throttle(
    session: aiohttp.ClientSession, ip: str, pw: str | None, percent: int
) -> tuple[bool, str]:
    """Set the throttle (percent of full power, 20..100)."""
    token = await _unlock(session, ip, pw)
    if not token:
        return (False, "unlock failed (miner off / wrong pw?)")
    try:
        async with session.post(
            f"{_base(ip)}/mining/throttle",
            json={"percent": int(percent)},
            headers={"Authorization": token},
            timeout=_TIMEOUT,
        ) as resp:
            ok = resp.status == 200
    except Exception as err:  # noqa: BLE001
        return (False, f"throttle failed: {err}")
    return (ok, f"HTTP {'200' if ok else 'error'}")
