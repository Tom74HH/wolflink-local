"""Two local holiday draft date/time fields, never automatic WOLF writes."""

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from .const import DOMAIN
from .mode_drafts import DraftEntity, draft


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        HolidayDateTime(c, key)
        for c in entry.runtime_data.coordinators
        if 22003500000 in c.definition.metadata
        for key in ("holiday_start", "holiday_end")
    )


class HolidayDateTime(DraftEntity, DateTimeEntity):
    @property
    def native_value(self):
        return draft(self.coordinator)[self.key]

    async def async_set_value(self, value):
        if value.tzinfo is None or value.second or value.microsecond:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="invalid_period"
            )
        draft(self.coordinator)[self.key] = dt_util.as_local(value)
        self.publish()
