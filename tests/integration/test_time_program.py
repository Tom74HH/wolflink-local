import unittest

from .load_api import WolfError
from wolflink_test_api.time_program import (
    parse_day,
    preview_day,
    describe_day,
    parameter_for,
)


def slots(*windows):
    return ";".join([*windows, *(["00:00-00:00"] * (5 - len(windows)))])


class ScheduleTests(unittest.TestCase):
    def test_empty_slots_and_full_day(self):
        self.assertEqual(parse_day(slots()), ())
        self.assertEqual(parse_day(slots("00:00-24:00"))[0].end, 1440)

    def test_preview_sorted_and_padded_never_transmitted(self):
        result = preview_day(
            "heating",
            1,
            "monday",
            [{"start": "17:00", "end": "22:00"}, {"start": "06:00", "end": "09:00"}],
        )
        self.assertEqual(result["parameter_id"], 32000000000)
        self.assertEqual(
            result["serialized_preview"], slots("06:00-09:00", "17:00-22:00")
        )
        self.assertFalse(result["transmitted"])
        self.assertFalse(result["write_supported"])

    def test_adjacent_windows_are_allowed(self):
        result = preview_day(
            "hot_water",
            3,
            "sunday",
            [{"start": "06:00", "end": "08:00"}, {"start": "08:00", "end": "09:00"}],
        )
        self.assertEqual(result["parameter_id"], 32004100000)

    def test_invalid_times_overlap_overnight_zero_duration_and_grid(self):
        cases = [
            [{"start": "23:00", "end": "01:00"}],
            [{"start": "24:00", "end": "24:00"}],
            [{"start": "06:00", "end": "24:15"}],
            [{"start": "6:00", "end": "08:00"}],
            [{"start": "06:00", "end": "06:00"}],
            [{"start": "06:05", "end": "08:00"}],
            [{"start": "06:00", "end": "08:00"}, {"start": "07:00", "end": "09:00"}],
        ]
        for windows in cases:
            with self.subTest(windows=windows):
                with self.assertRaises(WolfError):
                    preview_day("heating", 1, "monday", windows)

    def test_five_stored_active_windows_not_silently_discarded(self):
        raw = slots(
            "01:00-02:00", "03:00-04:00", "05:00-06:00", "07:00-08:00", "09:00-10:00"
        )
        result = describe_day(raw)
        self.assertEqual(len(result["windows"]), 5)
        self.assertFalse(result["editable_with_portal_policy"])
        with self.assertRaises(WolfError):
            preview_day("heating", 1, "monday", result["windows"])

    def test_existing_non_grid_minutes_are_not_rounded(self):
        result = describe_day(slots("06:07-09:13"))
        self.assertEqual(result["windows"], [{"start": "06:07", "end": "09:13"}])
        self.assertFalse(result["editable_with_portal_policy"])

    def test_bad_payloads_and_storage_capacity(self):
        for raw in [
            None,
            {},
            "",
            "00:00-00:00",
            slots("03:00-03:00"),
            slots("01:00-02:00") + ";",
        ]:
            with self.assertRaises(WolfError):
                parse_day(raw)
        for windows in [
            None,
            {},
            [True],
            [{"start": "06:00", "end": "07:00", "extra": "x"}],
        ]:
            with self.assertRaises(WolfError):
                preview_day("heating", 1, "monday", windows)

    def test_all_42_mappings_unique_and_invalid_targets_rejected(self):
        from wolflink_test_api.time_program import WEEKDAYS

        values = {
            parameter_for(area, program, day)
            for area in ("heating", "hot_water")
            for program in (1, 2, 3)
            for day in WEEKDAYS
        }
        self.assertEqual(len(values), 42)
        for args in [
            ("other", 1, "monday"),
            ("heating", True, "monday"),
            ("heating", 1, "unknown"),
            ("heating", 4, "monday"),
        ]:
            with self.assertRaises(WolfError):
                parameter_for(*args)
