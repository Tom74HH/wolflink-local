"""Explicit, validated party/holiday periods; independent of Home Assistant."""

from datetime import datetime
from .controls import WolfError, technical_id, decimal_value

MODES = {
    "party": (
        22003400000,
        3500,
        {
            "StartTime": 33000200000,
            "StartDate": 33000300000,
            "StopTime": 33000000000,
            "StopDate": 33000100000,
        },
    ),
    "holiday": (
        22003500000,
        3600,
        {
            "StartTime": 33000800000,
            "StartDate": 33000900000,
            "StopTime": 33000600000,
            "StopDate": 33000700000,
        },
    ),
}


def period_values(start, end, now):
    for value in (start, end, now):
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise WolfError("invalid_period")
    for value in (start, end):
        if not 2000 <= value.year <= 2099 or value.second or value.microsecond:
            raise WolfError("invalid_period")
        # The WOLF wire format has no offset/fold: reject ambiguous and nonexistent times.
        if value.replace(fold=0).utcoffset() != value.replace(fold=1).utcoffset():
            raise WolfError("invalid_period")
        if datetime.fromtimestamp(value.timestamp(), value.tzinfo).replace(
            tzinfo=None
        ) != value.replace(tzinfo=None):
            raise WolfError("invalid_period")
    if (
        start.tzinfo != now.tzinfo
        or end.tzinfo != now.tzinfo
        or start >= end
        or end <= now
    ):
        raise WolfError("invalid_period")
    return {
        "StartTime": start.strftime("%H:%M"),
        "StartDate": start.strftime("%d.%m.%Y"),
        "StopTime": end.strftime("%H:%M"),
        "StopDate": end.strftime("%d.%m.%Y"),
    }


def mode_metadata(mode, metadata):
    if mode not in MODES:
        raise WolfError("not_allowed")
    pid, bundle, roles = MODES[mode]
    parent = metadata.get(pid)
    if parent is None or parent.bundle_id != 1000:
        raise WolfError("metadata_changed")
    raw = parent.raw
    if (
        parent.value_id != pid
        or raw.get("ControlType") != 24
        or technical_id(raw.get("SubBundleId")) != bundle
        or raw.get("IsReadOnly") is not False
        or raw.get("NoDataPoint") is True
    ):
        raise WolfError("metadata_changed")
    items = raw.get("ListItems")
    try:
        if (
            not isinstance(items, list)
            or len(items) != 2
            or {decimal_value(r["Value"]) for r in items} != {0, 1}
        ):
            raise WolfError("metadata_changed")
    except (KeyError, TypeError, WolfError):
        raise WolfError("metadata_changed") from None
    children = raw.get("ChildParameterDescriptors")
    if not isinstance(children, list):
        raise WolfError("metadata_changed")
    mapped = {}
    for role, child_pid in roles.items():
        candidates = [
            c for c in children if isinstance(c, dict) and c.get("Group") == role
        ]
        if len(candidates) != 1:
            raise WolfError("metadata_changed")
        child = candidates[0]
        if (
            technical_id(child.get("ParameterId")) != child_pid
            or technical_id(child.get("ValueId")) != child_pid
            or child.get("ControlType") != (9 if role.endswith("Date") else 10)
            or child.get("IsReadOnly") is not False
            or child.get("NoDataPoint") is True
        ):
            raise WolfError("metadata_changed")
        mapped[role] = child_pid
    return pid, bundle, mapped
