"""Explicit v0.1.0 allowlist and validation; no Home Assistant dependency."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

BUNDLE = 1000
ONE_TIME_HOT_WATER = 22004200000


class WolfError(Exception):
    """Only static error codes are allowed to cross the API boundary."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ControlSpec:
    parameter_id: int
    key: str
    control_type: int
    options: tuple[tuple[int, str], ...] = ()
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    step: Decimal | None = None
    unit: str | None = None


CONTROLS = {
    ONE_TIME_HOT_WATER: ControlSpec(
        ONE_TIME_HOT_WATER, "one_time_hot_water", 1, ((0, "off"), (1, "on"))
    ),
    34002900000: ControlSpec(
        34002900000,
        "heating_mode",
        35,
        ((0, "standby"), (1, "automatic"), (2, "permanent"), (3, "economy")),
    ),
    35001200000: ControlSpec(
        35001200000,
        "hot_water_mode",
        35,
        ((0, "standby"), (1, "automatic"), (2, "permanent")),
    ),
    34001600000: ControlSpec(
        34001600000, "heating_program", 13, ((1, "1"), (2, "2"), (3, "3"))
    ),
    35000400000: ControlSpec(
        35000400000, "hot_water_program", 13, ((1, "1"), (2, "2"), (3, "3"))
    ),
    35000900000: ControlSpec(
        35000900000,
        "hot_water_target",
        6,
        minimum=Decimal("25"),
        maximum=Decimal("65"),
        step=Decimal("1"),
        unit="°C",
    ),
    34002600000: ControlSpec(
        34002600000,
        "temperature_offset",
        6,
        minimum=Decimal("-4"),
        maximum=Decimal("4"),
        step=Decimal("0.5"),
    ),
    34003500000: ControlSpec(
        34003500000,
        "heating_day_temperature",
        6,
        minimum=Decimal("5"),
        maximum=Decimal("30"),
        step=Decimal("0.5"),
        unit="°C",
    ),
}

# Individually verified daily IDs, ordered Monday to Sunday per program.
DAILY_IDS = (
    32000000000,
    32000100000,
    32000200000,
    32000300000,
    32000400000,
    32000500000,
    32000600000,
    32000700000,
    32000800000,
    32000900000,
    32001000000,
    32001100000,
    32001200000,
    32001300000,
    32001400000,
    32001500000,
    32001600000,
    32001700000,
    32001800000,
    32001900000,
    32002000000,
    32002100000,
    32002200000,
    32002300000,
    32002400000,
    32002500000,
    32002600000,
    32002700000,
    32002800000,
    32002900000,
    32003000000,
    32003100000,
    32003200000,
    32003300000,
    32003400000,
    32003500000,
    32003600000,
    32003700000,
    32003800000,
    32003900000,
    32004000000,
    32004100000,
)
FUTURE_IDS = frozenset(DAILY_IDS) | {
    22003400000,
    22003500000,
    33000000000,
    33000100000,
    33000200000,
    33000300000,
    33000400000,
    33000500000,
    33000600000,
    33000700000,
    33000800000,
    33000900000,
    33001000000,
    33001100000,
}


def decimal_value(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise WolfError("invalid_value")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise WolfError("invalid_value") from None
    if not result.is_finite():
        raise WolfError("invalid_value")
    return result


def technical_id(value: Any) -> int | None:
    # API identifiers are JSON integers. No float truncation or bool coercion.
    return value if type(value) is int and value > 0 else None


@dataclass(frozen=True)
class ParameterMeta:
    parameter_id: int
    value_id: int
    bundle_id: int
    name: str
    raw: dict[str, Any]


def walk_metadata(node: Any, bundle: int | None = None):
    if isinstance(node, dict):
        bundle = technical_id(node.get("BundleId")) or bundle
        pid, vid = (
            technical_id(node.get("ParameterId")),
            technical_id(node.get("ValueId")),
        )
        if pid is not None and vid is not None and bundle is not None:
            yield ParameterMeta(pid, vid, bundle, str(node.get("Name", "")), node)
        for value in node.values():
            if isinstance(value, (dict, list)):
                yield from walk_metadata(value, bundle)
    elif isinstance(node, list):
        for value in node:
            yield from walk_metadata(value, bundle)


def user_metadata(gui: Any) -> dict[int, ParameterMeta]:
    """Only the normal first menu, as in the upstream integration.

    Keep only unique, explicitly known bundle-1000 user parameters. Conflicting
    duplicate descriptors close the write path instead of choosing one.
    """
    if (
        not isinstance(gui, dict)
        or not isinstance(gui.get("MenuItems"), list)
        or not gui["MenuItems"]
    ):
        raise WolfError("malformed_response")
    found: dict[int, list[ParameterMeta]] = {}
    for item in walk_metadata(gui["MenuItems"][0]):
        if (
            item.bundle_id == BUNDLE
            and item.parameter_id in CONTROLS.keys() | FUTURE_IDS
        ):
            found.setdefault(item.parameter_id, []).append(item)
    return {pid: items[0] for pid, items in found.items() if len(items) == 1}


def live_bounds(
    spec: ControlSpec, meta: ParameterMeta
) -> tuple[Decimal, Decimal, Decimal]:
    if spec.minimum is None or spec.maximum is None or spec.step is None:
        raise WolfError("invalid_value")
    raw = meta.raw
    try:
        lo = decimal_value(raw.get("MinValueCondition", raw.get("MinValue")))
        hi = decimal_value(raw.get("MaxValueCondition", raw.get("MaxValue")))
        step = decimal_value(raw.get("StepWidth"))
    except WolfError:
        raise WolfError("metadata_changed") from None
    # Do not silently accept a different scale, grid, or looser safety range.
    if step != spec.step or lo < spec.minimum or hi > spec.maximum or lo > hi:
        raise WolfError("metadata_changed")
    if (lo - spec.minimum) % spec.step or (hi - spec.minimum) % spec.step:
        raise WolfError("metadata_changed")
    return lo, hi, step


def validate_write(parameter_id: int, value: Any, meta: ParameterMeta) -> int | float:
    spec = CONTROLS.get(parameter_id)
    if spec is None or meta.parameter_id != parameter_id or meta.bundle_id != BUNDLE:
        raise WolfError("not_allowed")
    if (
        meta.raw.get("IsReadOnly") is not False
        or meta.raw.get("NoDataPoint") is not False
    ):
        raise WolfError("not_writable")
    if (
        type(meta.raw.get("ControlType")) is not int
        or meta.raw["ControlType"] != spec.control_type
    ):
        raise WolfError("metadata_changed")
    number = decimal_value(value)
    if spec.options:
        items = meta.raw.get("ListItems")
        if not isinstance(items, list):
            raise WolfError("metadata_changed")
        try:
            reported = [decimal_value(item["Value"]) for item in items]
        except (WolfError, TypeError, KeyError):
            raise WolfError("metadata_changed") from None
        allowed = {Decimal(code) for code, _ in spec.options}
        if set(reported) != allowed or len(reported) != len(allowed):
            raise WolfError("metadata_changed")
        if number not in allowed:
            raise WolfError("invalid_value")
        for condition, fallback, direction in (
            ("MinValueCondition", "MinValue", "min"),
            ("MaxValueCondition", "MaxValue", "max"),
        ):
            if condition in meta.raw or fallback in meta.raw:
                try:
                    bound = decimal_value(
                        meta.raw.get(condition, meta.raw.get(fallback))
                    )
                except WolfError:
                    raise WolfError("metadata_changed") from None
                if (direction == "min" and number < bound) or (
                    direction == "max" and number > bound
                ):
                    raise WolfError("invalid_value")
    else:
        if (spec.unit is not None and meta.raw.get("Unit") != spec.unit) or (
            spec.unit is None and meta.raw.get("Unit") not in (None, "")
        ):
            raise WolfError("metadata_changed")
        lo, hi, step = live_bounds(spec, meta)
        if number < lo or number > hi or (number - lo) % step:
            raise WolfError("invalid_value")
    return int(number) if number == number.to_integral() else float(number)
