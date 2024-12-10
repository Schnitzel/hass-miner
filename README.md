# hass-miner

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![pre-commit][pre-commit-shield]][pre-commit]
[![Black][black-shield]][black]

[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance1-shield]][user1_profile]
[![Project Maintenance][maintenance2-shield]][user2_profile]

Control and monitor your Bitcoin Miners from Home Assistant. 

Great for Heat Reusage, Solar Mining or any usecase where you don't need your miners running 24/7 or with a specific wattage.

Works great in coordination with [ESPHome](https://www.home-assistant.io/integrations/esphome/) for Sensors (like temperature) and [Grafana](https://github.com/hassio-addons/addon-grafana) for Dashboards.

### Support for:
- Antminers
- Whatsminers
- Avalonminers
- Innosilicons
- Goldshells
- Auradine
- BitAxe
- IceRiver
- Hammer 
- Braiins Firmware
- Vnish Firmware
- ePIC Firmware
- HiveOS Firmware
- LuxOS Firmware
- Mara Firmware

[Full list of supported miners](https://pyasic.readthedocs.io/en/latest/miners/supported_types/).

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

Miner control and data is handled using [@UpstreamData](https://github.com/UpstreamData)'s [pyasic](https://github.com/UpstreamData/pyasic).

---

[integration_blueprint]: https://github.com/custom-components/integration_blueprint
[black]: https://github.com/psf/black
[black-shield]: https://img.shields.io/badge/code%20style-black-000000.svg?style=for-the-badge
[buymecoffee]: https://www.buymeacoffee.com/Schnitzel
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge
[commits-shield]: https://img.shields.io/github/commit-activity/y/Schnitzel/hass-miner.svg?style=for-the-badge
[commits]: https://github.com/Schnitzel/hass-miner/commits/main
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[exampleimg]: example.png
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/Schnitzel/hass-miner.svg?style=for-the-badge
[maintenance1-shield]: https://img.shields.io/badge/maintainer-%40Schnitzel-blue.svg?style=for-the-badge
[maintenance2-shield]: https://img.shields.io/badge/maintainer-%40b--rowan-blue.svg?style=for-the-badge
[pre-commit]: https://github.com/pre-commit/pre-commit
[pre-commit-shield]: https://img.shields.io/badge/pre--commit-enabled-brightgreen?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/Schnitzel/hass-miner.svg?style=for-the-badge
[releases]: https://github.com/Schnitzel/hass-miner/releases
[user1_profile]: https://github.com/Schnitzel
[user2_profile]: https://github.com/b-rowan
