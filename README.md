# hass-miner

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![pre-commit][pre-commit-shield]][pre-commit]
[![Ruff][ruff-shield]][ruff]
[![Conventional Commits][conventional-commits-shield]][conventional-commits]

[![hacs][hacs-shield]][hacs]
[![Project Maintenance][maintenance1-shield]][user1_profile]
[![Project Maintenance][maintenance2-shield]][user2_profile]

Control and monitor your Bitcoin Miners from Home Assistant.

[![Add Integration to Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=miner)

Great for Heat Reusage, Solar Mining or any usecase where you don't need your miners running 24/7 or with a specific wattage.

Works great in coordination with [ESPHome](https://www.home-assistant.io/integrations/esphome/) for Sensors (like temperature) and [Grafana](https://github.com/hassio-addons/addon-grafana) for Dashboards.

### Support for:

- Antminers
- Whatsminers
- Avalonminers
- Auradine
- BitAxe
- Braiins Firmware
- Vnish Firmware
- ePIC Firmware
- LuxOS Firmware
- Mara Firmware

[Full list of supported miners](https://256foundation.github.io/asic-rs/supported-devices/#support-matrix).

**This component will set up the following platforms -**

| Platform | Description               |
| -------- | ------------------------- |
| `sensor` | Show info from miner API. |
| `number` | Set Power Limit of Miner. |
| `switch` | Switch Miner on and off   |

**This component will add the following services -**

| Service           | Description                          |
| ----------------- | ------------------------------------ |
| `reboot`          | Reboot a miner by IP                 |
| `restart_backend` | Restart the backend of a miner by IP |

## Installation

Use HACS, add the custom repo https://github.com/Schnitzel/hass-miner to it

[![Installation and usage Video](http://img.youtube.com/vi/eL83eYLbgQM/0.jpg)](https://www.youtube.com/watch?v=6HwSQag7NU8)

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

## Credits

This project was generated from [@oncleben31](https://github.com/oncleben31)'s [Home Assistant Custom Component Cookiecutter](https://github.com/oncleben31/cookiecutter-homeassistant-custom-component) template.

Code template was mainly taken from [@Ludeeus](https://github.com/ludeeus)'s [integration_blueprint][integration_blueprint] template.

Miner control and data is handled using [@256foundation](https://github.com/256foundation)'s [asic-rs](https://github.com/256foundation/asic-rs).

---

[//]: # "Links"
[integration_blueprint]: https://github.com/custom-components/integration_blueprint
[ruff]: https://github.com/astral-sh/ruff
[buymecoffee]: https://www.buymeacoffee.com/Schnitzel
[commits]: https://github.com/Schnitzel/hass-miner/commits/main
[conventional-commits]: https://conventionalcommits.org
[hacs]: https://hacs.xyz
[discord]: https://discord.gg/Qa5fW2R
[releases]: https://github.com/Schnitzel/hass-miner/releases
[user1_profile]: https://github.com/Schnitzel
[user2_profile]: https://github.com/b-rowan
[forum]: https://community.home-assistant.io/
[pre-commit]: https://github.com/pre-commit/pre-commit
[//]: # "Shields"
[ruff-shield]: https://img.shields.io/badge/-Ruff-D7FF64.svg?style=for-the-badge&color=orange
[buymecoffee-shield]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate.svg?style=for-the-badge&color=orange
[commits-shield]: https://img.shields.io/github/commit-activity/y/Schnitzel/hass-miner.svg?style=for-the-badge&color=orange
[conventional-commits-shield]: https://img.shields.io/badge/Conventional%20Commits-1.0.0-orange?style=for-the-badge&color=orange
[hacs-shield]: https://img.shields.io/badge/HACS-Custom.svg?style=for-the-badge&color=orange
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge&color=orange
[forum-shield]: https://img.shields.io/badge/community-forum.svg?style=for-the-badge&color=orange
[license-shield]: https://img.shields.io/github/license/Schnitzel/hass-miner.svg?style=for-the-badge&color=orange
[maintenance1-shield]: https://img.shields.io/badge/maintainer-%40Schnitzel.svg?style=for-the-badge&color=orange
[maintenance2-shield]: https://img.shields.io/badge/maintainer-%40b--rowan.svg?style=for-the-badge&color=orange
[pre-commit-shield]: https://img.shields.io/badge/pre--commit-enabled?style=for-the-badge&color=orange
[releases-shield]: https://img.shields.io/github/release/Schnitzel/hass-miner.svg?style=for-the-badge&color=orange
[//]: # "Other"
[exampleimg]: example.png
