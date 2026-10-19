"""Lossless day parsing and conservative portal-compatible draft validation.

This module has no HTTP client or writing capability. Five storage slots are
confirmed for this installation; the portal UI limits edits to three windows.
"""

from dataclasses import dataclass
import re

from .controls import DAILY_IDS, WolfError

WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
EMPTY_SLOT = "00:00-00:00"
SLOT_COUNT = 5
PORTAL_MAX_WINDOWS = 3
PORTAL_GRID = 15


def minutes(value, *, endpoint=False):
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
        raise WolfError("invalid_schedule")
    hour, minute = map(int, value.split(":"))
    if hour == 24 and minute == 0 and endpoint:
        return 1440
    if not 0 <= hour < 24 or not 0 <= minute < 60:
        raise WolfError("invalid_schedule")
    return hour * 60 + minute


def time_label(value):
    return f"{value // 60:02d}:{value % 60:02d}"


@dataclass(frozen=True)
class Window:
    start: int
    end: int

    def as_dict(self):
        return {"start": time_label(self.start), "end": time_label(self.end)}


def validate_windows(windows, *, draft):
    if not isinstance(windows, list) or len(windows) > (
        PORTAL_MAX_WINDOWS if draft else SLOT_COUNT
    ):
        raise WolfError("invalid_schedule")
    parsed = []
    for window in windows:
        if not isinstance(window, dict) or set(window) != {"start", "end"}:
            raise WolfError("invalid_schedule")
        start = minutes(window["start"])
        end = minutes(window["end"], endpoint=True)
        if start >= end:
            raise WolfError("invalid_schedule")
        if draft and (start % PORTAL_GRID or end % PORTAL_GRID):
            raise WolfError("invalid_schedule")
        parsed.append(Window(start, end))
    parsed.sort(key=lambda window: window.start)
    # Touching boundaries are permitted by the portal's strict intersection test.
    if any(first.end > second.start for first, second in zip(parsed, parsed[1:])):
        raise WolfError("invalid_schedule")
    return tuple(parsed)


def parse_day(value):
    """Read without rounding, dropping extra active windows, or truncating slots."""
    if not isinstance(value, str) or len(value) > 255:
        raise WolfError("invalid_schedule")
    slots = value.split(";")
    if len(slots) != SLOT_COUNT:
        raise WolfError("invalid_schedule")
    windows = []
    for slot in slots:
        if slot == EMPTY_SLOT:
            continue
        parts = slot.split("-")
        if len(parts) != 2:
            raise WolfError("invalid_schedule")
        windows.append({"start": parts[0], "end": parts[1]})
    return validate_windows(windows, draft=False)


def parameter_for(area, program, weekday):
    if (
        area not in ("heating", "hot_water")
        or type(program) is not int
        or program not in (1, 2, 3)
        or weekday not in WEEKDAYS
    ):
        raise WolfError("invalid_schedule")
    index = (
        (0 if area == "heating" else 21) + (program - 1) * 7 + WEEKDAYS.index(weekday)
    )
    return DAILY_IDS[index]


def preview_day(area, program, weekday, windows):
    pid = parameter_for(area, program, weekday)
    parsed = validate_windows(windows, draft=True)
    slots = [
        f"{time_label(window.start)}-{time_label(window.end)}" for window in parsed
    ]
    slots.extend([EMPTY_SLOT] * (SLOT_COUNT - len(slots)))
    return {
        "area": area,
        "program": program,
        "weekday": weekday,
        "parameter_id": pid,
        "windows": [window.as_dict() for window in parsed],
        "serialized_preview": ";".join(slots),
        "storage_slots": SLOT_COUNT,
        "maximum_draft_windows": PORTAL_MAX_WINDOWS,
        "grid_minutes": PORTAL_GRID,
        "transmitted": False,
        "write_supported": False,
    }


def describe_day(value):
    parsed = parse_day(value)
    compatible = len(parsed) <= PORTAL_MAX_WINDOWS and all(
        window.start % PORTAL_GRID == 0 and window.end % PORTAL_GRID == 0
        for window in parsed
    )
    return {
        "windows": [window.as_dict() for window in parsed],
        "storage_slots": SLOT_COUNT,
        "editable_with_portal_policy": compatible,
        "write_supported": False,
    }


def schedule_writable(meta):
    """Only the diagnosed normal-user day representation is writable."""
    return (
        meta is not None
        and meta.bundle_id == 1000
        and meta.parameter_id in DAILY_IDS
        and meta.value_id == meta.parameter_id
        and meta.raw.get("ControlType") == 14
        and meta.raw.get("IsReadOnly") is False
        and meta.raw.get("NoDataPoint") is False
    )
