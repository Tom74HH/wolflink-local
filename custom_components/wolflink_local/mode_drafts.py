"""Local form fields. Editing these never writes to WOLF."""

from datetime import timedelta
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util
from .const import DOMAIN


def local_now():
    return dt_util.now().replace(second=0, microsecond=0)


def draft(coordinator):
    if not hasattr(coordinator, "mode_draft"):
        now = local_now()
        coordinator.mode_draft = {
            "party_minutes": 15,
            "holiday_start": now,
            "holiday_end": now + timedelta(hours=3),
        }
    return coordinator.mode_draft


class DraftEntity(Entity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key):
        self.coordinator = coordinator
        self.key = key
        draft(coordinator)
        self._attr_unique_id = f"{coordinator.device_key}:draft:{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_key)}
        )

    @property
    def extra_state_attributes(self):
        return {"local_draft": True, "transmitted": False}

    def publish(self):
        if self.hass is not None:
            self.async_write_ha_state()
