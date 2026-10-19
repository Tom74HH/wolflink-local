"""One-time hot water; duration and automatic reset belong to the WOLF regulator."""

from homeassistant.components.switch import SwitchEntity

from .controls import ONE_TIME_HOT_WATER, WolfError, decimal_value
from .entity import WolfEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        WolfHotWaterSwitch(coordinator)
        for coordinator in entry.runtime_data.coordinators
        if ONE_TIME_HOT_WATER in coordinator.definition.metadata
    )


class WolfHotWaterSwitch(WolfEntity, SwitchEntity):
    _attr_translation_key = "one_time_hot_water"
    _attr_icon = "mdi:water-boiler"

    def __init__(self, coordinator):
        super().__init__(coordinator, ONE_TIME_HOT_WATER, "switch")

    @property
    def is_on(self):
        try:
            value = decimal_value(self.raw_value)
        except WolfError:
            return None
        return bool(value) if value in (0, 1) else None

    @property
    def available(self):
        return super().available and self.is_on is not None

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_write_control(self.parameter_id, 1)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_write_control(self.parameter_id, 0)
