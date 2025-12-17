"""Lightweight test for `set_work_mode` device action."""
import asyncio

from custom_components.miner.device_action import async_call_action_from_config


class FakeServices:
    """Fake Home Assistant services registry capturing service calls."""

    def __init__(self):
        """Initialize the fake services store."""
        self.calls = []

    async def async_call(
        self, domain, service, service_data, blocking=True, context=None
    ):
        """Record an async service call with its parameters."""
        self.calls.append(
            {
                "domain": domain,
                "service": service,
                "service_data": service_data,
                "blocking": blocking,
                "context": context,
            }
        )


class FakeHass:
    """Fake Home Assistant core object exposing `services`."""

    def __init__(self):
        """Initialize the fake hass container with services."""
        self.services = FakeServices()


async def main():
    """Run a simple assertion flow to validate service call building."""
    hass = FakeHass()
    config = {
        "type": "set_work_mode",
        "domain": "miner",
        "device_id": "device-123",
        "mode": "normal",
    }
    variables = {}
    context = None

    await async_call_action_from_config(hass, config, variables, context)

    assert len(hass.services.calls) == 1, "Expected one service call"
    call = hass.services.calls[0]
    assert call["domain"] == "miner"
    assert call["service"] == "set_work_mode"
    assert call["service_data"]["device_id"] == ["device-123"]
    assert call["service_data"]["mode"] == "normal"


if __name__ == "__main__":
    asyncio.run(main())
