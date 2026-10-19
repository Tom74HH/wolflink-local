"""HA downloadable diagnostics without account, device identity, or values."""

from .const import VERSION
from .controls import CONTROLS, DAILY_IDS


def local_features(api):
    """Only fixed capability flags and known static errors, never raw payloads."""
    errors = getattr(api, "local_feature_errors", {})
    allowed = {"cannot_connect", "invalid_auth", "period_unconfirmed", "schedule_unavailable", "invalid_schedule", "malformed_response", "local_certificate_changed"}
    return {
        "schedule": getattr(api, "supports_schedule", None) is True,
        "timed_modes": getattr(api, "supports_timed_modes", None) is True,
        "errors": {key: value for key, value in errors.items() if key in ("periods", "schedule") and type(value) is str and value in allowed} if type(errors) is dict else {},
    }


async def async_get_config_entry_diagnostics(hass, entry):
    return {
        "version": VERSION,
        "read_only": entry.options.get("read_only", True) is not False,
        "systems": [
            {
                "reference": f"device_{index}",
                "last_update_success": coordinator.last_update_success,
                "sensor_count": len(coordinator.parameters),
                "local_features": local_features(coordinator.api),
                "present_controls": sorted(
                    CONTROLS.keys() & coordinator.definition.metadata.keys()
                ),
                "daily_schedule_count": len(
                    set(DAILY_IDS) & coordinator.definition.metadata.keys()
                ),
                "missing_controls": sorted(
                    pid
                    for pid in CONTROLS
                    if not coordinator.data
                    or (1000, pid) not in coordinator.data.values
                ),
            }
            for index, coordinator in enumerate(entry.runtime_data.coordinators, 1)
        ],
    }
