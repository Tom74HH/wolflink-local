"""Read-only daily schedules; v0.2 editor must supply its own validated writer."""

from homeassistant.components.sensor import SensorEntity

from .controls import DAILY_IDS
from .entity import WolfEntity

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class DailyScheduleSensor(WolfEntity, SensorEntity):
    # Actual schedule strings belong only in the user's HA, never in diagnostics.
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, parameter_id):
        super().__init__(coordinator, parameter_id, "daily_read_only")
        index = DAILY_IDS.index(parameter_id)
        self.area = "heating" if index < 21 else "hot_water"
        self.program = (index % 21) // 7 + 1
        self.day = DAYS[index % 7]
        self._attr_translation_key = "daily_schedule"
        self._attr_translation_placeholders = {
            "area": self.area,
            "program": str(self.program),
            "day": self.day,
        }

    @property
    def native_value(self):
        value = self.raw_value
        return value if isinstance(value, str) and len(value) <= 255 else None

    @property
    def available(self):
        return super().available and self.native_value is not None

    @property
    def extra_state_attributes(self):
        return {
            "parameter_id": self.parameter_id,
            "bundle_id": 1000,
            "area": self.area,
            "program": self.program,
            "day": self.day,
            "read_only": True,
            "format_validated_for_writing": False,
        }
