"""Path annoying home assistant dependency handling."""
from __future__ import annotations

import os
import site
import sys
import threading
from subprocess import PIPE
from subprocess import Popen

from homeassistant.util.package import _LOGGER
from homeassistant.util.package import is_virtual_env

_UV_ENV_PYTHON_VARS = (
    "UV_SYSTEM_PYTHON",
    "UV_PYTHON",
)


# Copy-paste of home assistant core install, but pre-releases are supported
def install_package(
    package: str,
    upgrade: bool = True,
    target: str | None = None,
    constraints: str | None = None,
    timeout: int | None = None,
    force_reinstall: bool = False,
    reinstall_package: str | None = None,
) -> bool:
    """Install a package on PyPi. Accepts pip compatible package strings.

    Return boolean if install successful.
    """
    _LOGGER.info("Attempting install of %s", package)
    env = os.environ.copy()
    args = [
        sys.executable,
        "-m",
        "uv",
        "pip",
        "install",
        "--quiet",
        package,
        # Allow prereleases in sub-packages
        "--prerelease=allow",
        # We need to use unsafe-first-match for custom components
        # which can use a different version of a package than the one
        # we have built the wheel for.
        "--index-strategy",
        "unsafe-first-match",
    ]
    if timeout:
        env["HTTP_TIMEOUT"] = str(timeout)
    if upgrade:
        args.append("--upgrade")
    if force_reinstall:
        args.append("--reinstall")
    if reinstall_package:
        # Reinstall only this distribution, leaving already-imported shared
        # dependencies (cryptography, pydantic, httpx, ...) untouched on disk.
        args += ["--reinstall-package", reinstall_package]
    if constraints is not None:
        args += ["--constraint", constraints]
    if target:
        abs_target = os.path.abspath(target)
        args += ["--target", abs_target]
    elif (
        not is_virtual_env()
        and not (any(var in env for var in _UV_ENV_PYTHON_VARS))
        and (abs_target := site.getusersitepackages())
    ):
        # Pip compatibility
        # Uv has currently no support for --user
        # See https://github.com/astral-sh/uv/issues/2077
        # Using workaround to install to site-packages
        # https://github.com/astral-sh/uv/issues/2077#issuecomment-2150406001
        args += ["--python", sys.executable, "--target", abs_target]

    _LOGGER.debug("Running uv pip command: args=%s", args)
    with Popen(
        args,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
        env=env,
        close_fds=False,  # required for posix_spawn
    ) as process:
        _, stderr = process.communicate()
        if process.returncode != 0:
            _LOGGER.error(
                "Unable to install package %s: %s",
                package,
                stderr.decode("utf-8").lstrip().strip(),
            )
            return False

    return True


_PYASIC_LOCK = threading.Lock()


def _import_pyasic(expected_version: str):
    """Import pyasic and validate it; raise ImportError if unusable."""
    from importlib.metadata import PackageNotFoundError, version

    import pyasic

    if not hasattr(pyasic, "get_miner"):
        raise ImportError("pyasic module incomplete")
    try:
        installed = version("pyasic")
    except PackageNotFoundError as err:
        raise ImportError("pyasic metadata missing") from err
    if installed != expected_version:
        raise ImportError(f"pyasic {installed} != required {expected_version}")
    return pyasic


def _purge_pyasic_modules() -> None:
    for mod_name in list(sys.modules):
        if mod_name == "pyasic" or mod_name.startswith("pyasic."):
            del sys.modules[mod_name]


def ensure_pyasic(expected_version: str):
    """Return an importable, correctly-versioned pyasic, installing if needed.

    Must be called from an executor thread. Serialized with a process-wide lock:
    on a fresh container (e.g. after a Core update) several config entries set up
    concurrently, and without the lock one entry runs ``uv pip install --reinstall``
    while others import a half-unpacked package -> ModuleNotFoundError -> setup_error.
    """
    with _PYASIC_LOCK:
        try:
            return _import_pyasic(expected_version)
        except Exception as err:  # noqa: BLE001 - any import failure means reinstall
            _LOGGER.info("pyasic unusable (%s); (re)installing %s", err, expected_version)

        _purge_pyasic_modules()
        if not install_package(
            f"pyasic=={expected_version}",
            upgrade=False,
            reinstall_package="pyasic",
        ):
            raise ImportError(f"Failed to install pyasic=={expected_version}")
        _purge_pyasic_modules()
        return _import_pyasic(expected_version)
