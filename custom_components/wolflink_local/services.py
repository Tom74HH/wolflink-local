"""Read and preview time programs. Neither action has a write path."""

import probatio

from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .controls import WolfError, decimal_value
from .time_program import (
    WEEKDAYS,
    describe_day,
    parameter_for,
    preview_day,
    schedule_writable,
)


def program_number(value):
    if type(value) not in (int, float) or value not in (1, 2, 3):
        raise probatio.Invalid("Program must be 1, 2 or 3")
    return int(value)


READ_SCHEMA = probatio.Schema(
    {
        probatio.Required("device_id"): str,
        probatio.Required("area"): probatio.In(("heating", "hot_water")),
        probatio.Required("program"): program_number,
    }
)
PREVIEW_SCHEMA = probatio.Schema(
    {
        probatio.Required("area"): probatio.In(("heating", "hot_water")),
        probatio.Required("program"): program_number,
        probatio.Required("weekday"): probatio.In(WEEKDAYS),
        probatio.Required("windows"): list,
    }
)


WRITE_SCHEMA = READ_SCHEMA.extend(
    {
        probatio.Required("weekday"): probatio.In(WEEKDAYS),
        probatio.Required("windows"): list,
        probatio.Required("expected"): str,
    }
)


def translated_error(code):
    return HomeAssistantError(translation_domain=DOMAIN, translation_key=code)


def register_services(hass):
    if hass.services.has_service(DOMAIN, "get_time_program"):
        return

    def resolve_coordinator(call):
        device = dr.async_get(hass).async_get(call.data["device_id"])
        coordinator = None
        if device is not None:
            for entry in hass.config_entries.async_loaded_entries(DOMAIN):
                for candidate in entry.runtime_data.coordinators:
                    if (DOMAIN, candidate.device_key) in device.identifiers:
                        coordinator = candidate
                        break
        if coordinator is None:
            raise translated_error("schedule_device_not_found")
        return coordinator

    async def get_time_program(call):
        coordinator = resolve_coordinator(call)
        if getattr(coordinator.api, "supports_schedule", None) is True:
            from .api import Snapshot

            try:
                fresh = await coordinator.api.read_time_program(
                    coordinator.device, call.data["area"], call.data["program"]
                )
            except WolfError as exc:
                raise translated_error(exc.code) from None
            values = dict(coordinator.data.values) if coordinator.data else {}
            values.update(fresh.values)
            snapshot = Snapshot(values)
            coordinator._reconcile_confirmations(snapshot)
            coordinator.async_set_updated_data(snapshot)
        else:
            await coordinator.async_request_refresh()
        if not coordinator.last_update_success or coordinator.data is None:
            raise translated_error("schedule_unavailable")
        area, program = call.data["area"], call.data["program"]
        days = {}
        for weekday in WEEKDAYS:
            pid = parameter_for(area, program, weekday)
            value = coordinator.data.values.get((1000, pid))
            acknowledged = (
                value is None and pid in coordinator.api.schedule_acknowledgements
            )
            if acknowledged:
                value = coordinator.api.schedule_acknowledgements[pid]
            try:
                days[weekday] = {
                    "parameter_id": pid,
                    "status": "ok",
                    **describe_day(value),
                    "serialized": value,
                    "write_supported": schedule_writable(
                        coordinator.definition.metadata.get(pid)
                    ),
                    "write_status": "awaiting_confirmation"
                    if acknowledged
                    else coordinator.control_write_status.get(pid, "reported"),
                }
            except WolfError:
                days[weekday] = {
                    "parameter_id": pid,
                    "status": "unavailable_or_unsupported_format",
                    "write_supported": False,
                }
        active_pid = 34001600000 if area == "heating" else 35000400000
        try:
            active = decimal_value(coordinator.data.values.get((1000, active_pid)))
            active = int(active) if active in (1, 2, 3) else None
        except WolfError:
            active = None
        return {
            "area": area,
            "program": program,
            "active_program": active,
            "days": days,
            "complete": all(day["status"] == "ok" for day in days.values()),
            "write_supported": True,
            "read_only": coordinator.read_only,
        }

    async def preview_time_program_day(call):
        try:
            return preview_day(
                call.data["area"],
                call.data["program"],
                call.data["weekday"],
                call.data["windows"],
            )
        except WolfError:
            raise translated_error("invalid_schedule") from None

    async def write_time_program_day(call):
        coordinator = resolve_coordinator(call)
        return await coordinator.async_write_schedule_day(
            call.data["area"],
            call.data["program"],
            call.data["weekday"],
            call.data["windows"],
            call.data["expected"],
        )

    hass.services.async_register(
        DOMAIN,
        "write_time_program_day",
        write_time_program_day,
        schema=WRITE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "get_time_program",
        get_time_program,
        schema=READ_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "preview_time_program_day",
        preview_time_program_day,
        schema=PREVIEW_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


def unregister_services_if_unused(hass):
    if any(hass.config_entries.async_loaded_entries(DOMAIN)):
        return
    for name in (
        "get_time_program",
        "preview_time_program_day",
        "write_time_program_day",
    ):
        hass.services.async_remove(DOMAIN, name)
