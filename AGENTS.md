# Repository Instructions

## Scope

- This is a Home Assistant custom integration, not a standalone service.
- Runtime code lives in `custom_components/miner/`; bootstrap is `__init__.py`, polling is in `coordinator.py`, and services are in `services.py`.
- The integration exposes `sensor`, `switch`, and `number` platforms. `select.py` exists but is intentionally not registered.
- Miner discovery and control use `pyasic`; the coordinator polls every 10 seconds.

## Commands

- `./scripts/setup` prepares the development environment.
- `./scripts/develop` starts Home Assistant with the local `config/` directory.
- `python3 -m ruff check .` is the non-mutating lint check.
- `./scripts/lint` runs Ruff with `--fix` and modifies files; inspect the diff afterward.
- `pre-commit install` and `pre-commit run --all-files` run repository hooks.
- `python3 scripts/test_device_action_workmode.py` is the available device-action test. There is no conventional unit-test suite; most behavior requires a reachable physical or emulated miner.

## CI and Dependencies

- CI runs Ruff, HACS validation, and Hassfest; it does not provide a full integration test environment.
- Check the Python-version mismatch before changing tooling: `pyproject.toml` requires `>=3.13.2,<3.14`, while one CI workflow uses Python 3.12.
- Keep the `pyasic` version contract synchronized across `custom_components/miner/const.py`, `pyproject.toml`, and `requirements.txt`. Runtime code can reinstall the required version, so startup may need network access and package-install permissions.

## Safety

- Do not commit `.venv`, Home Assistant databases, logs, `.storage`, `__pycache__`, credentials, or local runtime artifacts.
- Never log miner credentials or full `pyasic` objects at debug level.
- Read relevant integration code and preserve existing config-entry behavior before changing entity IDs, services, polling, or credential handling.
