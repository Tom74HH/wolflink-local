"""Shared device identity and actual-value access."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .controls import BUNDLE


class WolfEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, parameter_id, suffix):
        super().__init__(coordinator)
        self.parameter_id = parameter_id
        self._attr_unique_id = f"{coordinator.device_key}:{parameter_id}:{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_key)},
            manufacturer=MANUFACTURER,
            name=coordinator.device.name,
            configuration_url=f"http://{coordinator.entry.data['host']}/",
        )

    @property
    def raw_value(self):
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.values.get((BUNDLE, self.parameter_id))

    @property
    def available(self):
        return super().available and self.raw_value is not None

    @property
    def extra_state_attributes(self):
        return {
            "parameter_id": self.parameter_id,
            "bundle_id": BUNDLE,
            "read_only": self.coordinator.read_only,
            "write_status": self.coordinator.control_write_status.get(
                self.parameter_id, "reported"
            ),
        }
