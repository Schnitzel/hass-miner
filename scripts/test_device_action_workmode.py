import asyncio
from types import SimpleNamespace

from custom_components.miner.device_action import async_call_action_from_config

class FakeServices:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, service_data, blocking=True, context=None):
        self.calls.append({
            "domain": domain,
            "service": service,
            "service_data": service_data,
            "blocking": blocking,
            "context": context,
        })

class FakeHass:
    def __init__(self):
        self.services = FakeServices()

async def main():
    hass = FakeHass()
    config = {
        "type": "set_work_mode",
        "domain": "miner",
        "device_id": "device-123",
        "mode": "medium",
        # entity_id is not used for device actions anymore in our call path
        "entity_id": "sensor.fake",
    }
    variables = {}
    context = None

    await async_call_action_from_config(hass, config, variables, context)

    assert len(hass.services.calls) == 1, "Expected one service call"
    call = hass.services.calls[0]
    print("Service call:", call)
    assert call["domain"] == "miner"
    assert call["service"] == "set_work_mode"
    assert call["service_data"]["device_id"] == ["device-123"]
    assert call["service_data"]["mode"] == "medium"
    print("Test passed: device_action set_work_mode builds correct service call")

if __name__ == "__main__":
    asyncio.run(main())
