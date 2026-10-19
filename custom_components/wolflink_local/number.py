"""Two validated user setpoints, using only the preferred IDs."""

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode

from .controls import CONTROLS, WolfError, decimal_value, live_bounds
from .entity import WolfEntity
from .mode_drafts import DraftEntity, draft


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        WolfNumber(coordinator, spec)
        for coordinator in entry.runtime_data.coordinators
        for spec in CONTROLS.values()
        if not spec.options and spec.parameter_id in coordinator.definition.metadata
    )
    async_add_entities(
        PartyDuration(c, "party_minutes")
        for c in entry.runtime_data.coordinators
        if 22003400000 in c.definition.metadata
    )


class PartyDuration(DraftEntity, NumberEntity):
    _attr_native_min_value = 15
    _attr_native_max_value = 1440
    _attr_native_step = 15
    _attr_native_unit_of_measurement = "min"
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:timer-outline"

    @property
    def native_value(self):
        return draft(self.coordinator)["party_minutes"]

    async def async_set_native_value(self, value):
        from homeassistant.exceptions import HomeAssistantError
        from .const import DOMAIN

        try:
            number = decimal_value(value)
            if number < 15 or number > 1440 or number % 15:
                raise WolfError("invalid_value")
        except WolfError:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="invalid_value"
            ) from None
        draft(self.coordinator)["party_minutes"] = int(number)
        self.publish()


class WolfNumber(WolfEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, spec):
        super().__init__(coordinator, spec.parameter_id, "number")
        self.spec = spec
        self._attr_translation_key = spec.key
        self._attr_native_unit_of_measurement = spec.unit
        if spec.unit == "°C":
            self._attr_device_class = NumberDeviceClass.TEMPERATURE

    @property
    def native_value(self):
        try:
            return float(decimal_value(self.raw_value))
        except WolfError:
            return None

    def _bounds(self):
        meta = self.coordinator.definition.metadata.get(self.parameter_id)
        if meta is not None:
            try:
                return live_bounds(self.spec, meta)
            except WolfError:
                pass
        return self.spec.minimum, self.spec.maximum, self.spec.step

    @property
    def native_min_value(self):
        return float(self._bounds()[0])

    @property
    def native_max_value(self):
        return float(self._bounds()[1])

    @property
    def native_step(self):
        return float(self._bounds()[2])

    @property
    def available(self):
        return super().available and self.native_value is not None

    async def async_set_native_value(self, value):
        await self.coordinator.async_write_control(self.parameter_id, value)
