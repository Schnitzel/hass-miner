"""Tests for patch.ensure_pyasic (install race / dependency clobbering fix)."""
from __future__ import annotations

import sys
import threading
from unittest.mock import patch

import pytest

from custom_components.miner import patch as miner_patch

# grab the real function before the autouse fixture in conftest mocks it
_REAL_INSTALL_PACKAGE = miner_patch.install_package


def _real_version():
    from importlib.metadata import version

    return version("pyasic")


def test_ensure_pyasic_noop_when_installed():
    """Correct version present -> no install call, module returned."""
    with patch.object(miner_patch, "install_package") as inst:
        mod = miner_patch.ensure_pyasic(_real_version())
    assert mod.__name__ == "pyasic"
    assert hasattr(mod, "get_miner")
    inst.assert_not_called()


def test_ensure_pyasic_reinstalls_only_pyasic_on_version_mismatch():
    """Wrong version -> exactly one install of *pyasic only*, no --upgrade/--reinstall of deps."""
    import pyasic as real_pyasic

    calls = []

    def fake_install(package, **kw):
        calls.append((package, kw))
        return True

    # first import check fails (mismatch), post-install check succeeds
    with patch.object(miner_patch, "install_package", side_effect=fake_install), patch.object(
        miner_patch,
        "_import_pyasic",
        side_effect=[ImportError("pyasic 0.0.0 != required X"), real_pyasic],
    ):
        mod = miner_patch.ensure_pyasic("X")
    assert mod is real_pyasic
    assert calls == [("pyasic==X", {"upgrade": False, "reinstall_package": "pyasic"})]

def test_ensure_pyasic_raises_when_install_fails():
    with patch.object(miner_patch, "install_package", return_value=False), patch.object(
        miner_patch, "_import_pyasic", side_effect=ImportError("missing")
    ), pytest.raises(ImportError, match="Failed to install"):
        miner_patch.ensure_pyasic("9.9.9")

def test_ensure_pyasic_serialized_single_install_under_contention():
    """N concurrent callers with a missing package -> exactly one install."""
    installs = []
    lock_probe = {"concurrent": 0, "max": 0}
    guard = threading.Lock()

    def fake_install(package, **kw):
        with guard:
            lock_probe["concurrent"] += 1
            lock_probe["max"] = max(lock_probe["max"], lock_probe["concurrent"])
        installs.append(package)
        import time

        time.sleep(0.05)  # widen the window
        with guard:
            lock_probe["concurrent"] -= 1
        return True

    results, errors = [], []
    import pyasic as real_pyasic

    state = {"installed": False}

    def fake_import(_expected):
        # Until the (single) install has happened, every import attempt fails.
        if not state["installed"]:
            raise ImportError("not installed")
        return real_pyasic

    def fake_install_and_mark(package, **kw):
        r = fake_install(package, **kw)
        state["installed"] = True
        return r

    def worker():
        try:
            results.append(miner_patch.ensure_pyasic("X").__name__)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    with patch.object(
        miner_patch, "install_package", side_effect=fake_install_and_mark
    ), patch.object(miner_patch, "_import_pyasic", side_effect=fake_import):
        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert errors == []
    assert results == ["pyasic"] * 6
    assert len(installs) == 1, "only the first caller should install"
    assert lock_probe["max"] == 1, "installs must never overlap"


def test_install_package_uses_reinstall_package_flag_not_full_reinstall():
    """The uv command line must scope the reinstall to a single distribution."""
    real_install_package = _REAL_INSTALL_PACKAGE
    captured = {}

    class FakeProc:
        returncode = 0

        def __init__(self, args, **kw):
            captured["args"] = args

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def communicate(self):
            return b"", b""

    with patch.object(miner_patch, "Popen", FakeProc):
        ok = real_install_package(
            "pyasic==1.2.3", upgrade=False, reinstall_package="pyasic"
        )
    assert ok
    args = captured["args"]
    assert "--reinstall-package" in args
    assert args[args.index("--reinstall-package") + 1] == "pyasic"
    assert "--reinstall" not in args
    assert "--upgrade" not in args
    assert "--prerelease=allow" in args


def test_purge_pyasic_modules_only_touches_pyasic():
    sys.modules["pyasic_fake_sibling"] = object()  # must survive (prefix match trap)
    sys.modules["pyasic.zzz_test"] = object()
    try:
        miner_patch._purge_pyasic_modules()
        assert "pyasic.zzz_test" not in sys.modules
        assert "pyasic_fake_sibling" in sys.modules
    finally:
        sys.modules.pop("pyasic_fake_sibling", None)
        sys.modules.pop("pyasic.zzz_test", None)
