import unittest
from .load_api import (
    CONTROLS,
    DAILY_IDS,
    ParameterMeta,
    WolfError,
    validate_write,
    user_metadata,
)


def raw_control(pid):
    spec = CONTROLS[pid]
    raw = {
        "ParameterId": pid,
        "ValueId": pid,
        "BundleId": 1000,
        "ControlType": spec.control_type,
        "IsReadOnly": False,
        "NoDataPoint": False,
        "Name": spec.key,
    }
    if spec.options:
        raw["ListItems"] = [
            {"Value": code, "DisplayText": label} for code, label in spec.options
        ]
    else:
        raw.update(
            MinValue=float(spec.minimum),
            MaxValue=float(spec.maximum),
            MinValueCondition=str(spec.minimum),
            MaxValueCondition=str(spec.maximum),
            StepWidth=float(spec.step),
        )
        if spec.unit:
            raw["Unit"] = spec.unit
    return raw


def meta(pid, **changes):
    raw = dict(raw_control(pid), **changes)
    return ParameterMeta(pid, raw["ValueId"], raw["BundleId"], raw["Name"], raw)


class ValidationTests(unittest.TestCase):
    def test_exact_eight_allowed_controls_no_alternatives(self):
        self.assertEqual(
            set(CONTROLS),
            {
                22004200000,
                34002900000,
                35001200000,
                34001600000,
                35000400000,
                35000900000,
                34002600000,
                34003500000,
            },
        )
        self.assertEqual(len(set(DAILY_IDS)), 42)

    def test_every_declared_option_validates(self):
        for pid, spec in CONTROLS.items():
            for code, _ in spec.options:
                self.assertEqual(validate_write(pid, code, meta(pid)), code)

    def test_number_bounds_steps_and_finite_values(self):
        for pid, good, bad in [
            (35000900000, [25, 60, 65], [24, 66, 25.5]),
            (34002600000, [-4, -0.5, 0, 4], [-4.5, 4.5, 0.25]),
        ]:
            for value in good:
                self.assertEqual(validate_write(pid, value, meta(pid)), value)
            for value in bad + [True, None, {}, float("nan"), float("inf"), "bad"]:
                with self.subTest(pid=pid, value=value):
                    with self.assertRaises(WolfError):
                        validate_write(pid, value, meta(pid))

    def test_conditions_take_precedence_and_can_only_narrow(self):
        pid = 35000900000
        self.assertEqual(validate_write(pid, 40, meta(pid, MinValueCondition="40")), 40)
        for changes in [
            {"MinValueCondition": "40"},
            {"MinValueCondition": "expression"},
            {"MaxValueCondition": "70"},
            {"StepWidth": 0.5},
        ]:
            with self.assertRaises(WolfError):
                validate_write(pid, 25, meta(pid, **changes))

    def test_enum_condition_and_number_unit_changes_block_writes(self):
        with self.assertRaises(WolfError):
            validate_write(34002900000, 3, meta(34002900000, MaxValueCondition="2"))
        with self.assertRaises(WolfError):
            validate_write(35000900000, 40, meta(35000900000, Unit="°F"))

    def test_missing_false_permissions_or_changed_type_fail_closed(self):
        pid = 34002900000
        for changes in [
            {"IsReadOnly": True},
            {"IsReadOnly": None},
            {"IsReadOnly": "false"},
            {"NoDataPoint": True},
            {"ControlType": 31},
            {"BundleId": 3000},
            {"ListItems": [{"Value": 0}]},
        ]:
            with self.assertRaises(WolfError):
                validate_write(pid, 0, meta(pid, **changes))

    def test_invalid_choice_and_non_allowlisted_parameter_rejected(self):
        for pid in [34003200000, 35001400000, 22003400000, 32000000000, 18011500001]:
            with self.assertRaises(WolfError):
                validate_write(pid, 1, meta(34002900000))
        with self.assertRaises(WolfError):
            validate_write(34002900000, 4, meta(34002900000))

    def test_only_user_menu_bundle_and_unambiguous_metadata(self):
        r = raw_control(34002900000)
        expert = raw_control(35001200000)
        gui = {
            "MenuItems": [
                {"TabViews": [{"BundleId": 1000, "ParameterDescriptors": [r]}]},
                {"TabViews": [{"ParameterDescriptors": [expert]}]},
            ]
        }
        self.assertEqual(set(user_metadata(gui)), {34002900000})
        gui["MenuItems"][0]["TabViews"][0]["ParameterDescriptors"].append(r.copy())
        self.assertEqual(user_metadata(gui), {})
