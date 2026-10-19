"""Four confirmed user selection parameters; no alternative write IDs."""

import asyncio

from homeassistant.components.select import SelectEntity

from .controls import CONTROLS, ONE_TIME_HOT_WATER, WolfError, decimal_value
from .entity import WolfEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        WolfSelect(coordinator, spec)
        for coordinator in entry.runtime_data.coordinators
        for spec in CONTROLS.values()
        if spec.options
        and spec.parameter_id != ONE_TIME_HOT_WATER
        and spec.parameter_id in coordinator.definition.metadata
    )


class WolfSelect(WolfEntity, SelectEntity):
    def __init__(self, coordinator, spec):
        super().__init__(coordinator, spec.parameter_id, "select")
        self.spec = spec
        self._attr_translation_key = spec.key
        self._attr_options = [name for _, name in spec.options]
        self._pending_option = None
        self._selection_lock = asyncio.Lock()

    @property
    def current_option(self):
        if self._pending_option is not None:
            return self._pending_option
        return self.confirmed_option

    @property
    def confirmed_option(self):
        try:
            raw = decimal_value(self.raw_value)
        except WolfError:
            return None
        return next((name for code, name in self.spec.options if code == raw), None)

    @property
    def extra_state_attributes(self):
        return {
            **super().extra_state_attributes,
            "write_pending": self._pending_option is not None,
            "confirmed_option": self.confirmed_option,
            "Bestätigung": "Ausstehend"
            if self._pending_option is not None
            else "Keine ausstehend",
        }

    @property
    def available(self):
        return super().available and self.current_option is not None

    async def async_select_option(self, option):
        code = next((code for code, name in self.spec.options if name == option), None)
        if code is None:
            from homeassistant.exceptions import HomeAssistantError
            from .const import DOMAIN

            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="invalid_value"
            )
        async with self._selection_lock:
            # Only operating modes show the user's pending choice immediately.
            # Actual values stay in the coordinator and the read-only sensors.
            pending = (
                self.parameter_id in (34002900000, 35001200000)
                and not self.coordinator.read_only
            )
            if pending:
                self._pending_option = option
                if self.hass is not None:
                    self.async_write_ha_state()
            try:
                await self.coordinator.async_write_control(self.parameter_id, code)
            finally:
                self._pending_option = None
                if pending and self.hass is not None:
                    self.async_write_ha_state()
