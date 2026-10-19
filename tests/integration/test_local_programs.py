"""Native BM-2 periods/day programs: real wire layouts, simulated heater only."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import json
from pathlib import Path
import struct
from types import SimpleNamespace as NS
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock, patch
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from custom_components.wolflink_local.local_api import LocalWolfApi
from custom_components.wolflink_local.local_programs import (
    decode_day,
    encode_day,
    decode_period_word,
    encode_period_word,
    day_attributes,
)
from custom_components.wolflink_local.controls import DAILY_IDS, WolfError
from custom_components.wolflink_local.time_program import preview_day, parse_day


ORIGINAL = struct.pack(
    "<HHHHHHHHHH", 270, 480, 900, 1320, 65535, 65535, 65535, 65535, 65535, 65535
)
WINDOWS = [{"start": "04:45", "end": "08:00"}, {"start": "15:00", "end": "22:00"}]


class FormatTests(TestCase):
    def test_day_roundtrip_preserves_empty_and_unused_bytes(self):
        target = preview_day("heating", 1, "monday", WINDOWS)["serialized_preview"]
        encoded = encode_day(target, ORIGINAL)
        self.assertEqual(encoded[4:], ORIGINAL[4:])
        self.assertEqual(struct.unpack("<H", encoded[:2])[0], 285)
        restored = encode_day(decode_day(ORIGINAL), encoded)
        self.assertEqual(restored, ORIGINAL)

    def test_no_silent_extra_window_loss_or_midnight_rounding(self):
        for data in (
            b"",
            bytes(19),
            bytes(21),
            struct.pack("<HH", 100, 50) + bytes(16),
        ):
            with self.assertRaises(WolfError):
                decode_day(data)
        four = struct.pack("<HHHHHHHHHH", 60, 120, 180, 240, 300, 360, 420, 480, 0, 0)
        with self.assertRaises(WolfError):
            encode_day(decode_day(ORIGINAL), four)
        target = preview_day(
            "heating", 1, "monday", [{"start": "04:30", "end": "24:00"}]
        )["serialized_preview"]
        with self.assertRaisesRegex(WolfError, "local_midnight_unsupported"):
            encode_day(target, ORIGINAL)

    def test_all_42_day_addresses(self):
        values = [day_attributes(pid, "0x35") for pid in DAILY_IDS]
        self.assertEqual(len({tuple(v.items()) for v in values}), 42)
        self.assertEqual(
            values[0], {"ba": "0x35", "hp": "1", "ty": "0", "hk": "0", "d": "1"}
        )
        self.assertEqual(values[6]["d"], "0")
        self.assertEqual(values[21]["ty"], "1")
        self.assertEqual(values[41]["hp"], "3")

    def test_period_encoding_leap_days_limits_and_time(self):
        for value in ("01.01.2000", "29.02.2024", "31.12.2099"):
            self.assertEqual(
                decode_period_word(encode_period_word(value, "date"), "date"), value
            )
        for value in ("00:00", "12:46", "23:59"):
            self.assertEqual(
                decode_period_word(encode_period_word(value, "time"), "time"), value
            )
        for value, kind in [
            ("29.02.2023", "date"),
            ("01.01.2100", "date"),
            ("24:00", "time"),
            ("12:60", "time"),
        ]:
            with self.assertRaises(WolfError):
                encode_period_word(value, kind)


class FakeSession:
    def __init__(self, now):
        self.sequence = 0
        self.days = {}
        self.words = {}
        self.writes = []
        self.update_day = True
        self.fail_period = False
        self.wrong_response = False
        self.words.update(
            {
                10145: 0,
                10150: 0,
                10160: encode_period_word(now.strftime("%d.%m.%Y"), "date"),
                10161: encode_period_word(now.strftime("%H:%M"), "time"),
            }
        )

    async def telegrams(self, address, numbers):
        return {number: self.words.get(number, 0) for number in numbers}

    async def request(self, kind, request):
        response = ET.Element("tbres", bn=request.get("bn"), st="OK")
        row = request[0]
        if row.tag.startswith("s03f"):
            key = tuple(row.get(k) for k in ("hp", "ty", "hk", "d"))
            raw = self.days.get(key, ORIGINAL)
            write = row.tag == "s03f3wr"
            if write:
                self.writes.append(("day", key, bytes.fromhex(row.get("db"))))
                if self.update_day:
                    self.days[key] = bytes.fromhex(row.get("db"))
            attributes = {k: row.get(k) for k in ("ba", "hp", "ty", "hk", "d", "se")}
            attributes.update(st="OK", db=raw.hex())
            if self.wrong_response:
                attributes["d"] = "6"
            ET.SubElement(response, "s03f3ac" if write else "s03f2rs", attributes)
        else:
            values = {
                int(row.get("in")): int(row.get("dl"), 0) | (int(row.get("dh"), 0) << 8)
                for row in request
            }
            self.writes.append(("words", values))
            self.words.update(values)
            if self.fail_period and len(values) > 1:
                raise WolfError("write_failed")
            for row in request:
                ET.SubElement(response, "iac", {**row.attrib, "st": "OK"})
        return response


class ProgramTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = datetime(2026, 10, 16, 14, tzinfo=ZoneInfo("Europe/Berlin"))
        self.session = FakeSession(self.now)
        parameters = json.loads(
            Path("custom_components/wolflink_local/local/parameters.json").read_text(
                encoding="utf8"
            )
        )
        self.api = LocalWolfApi("192.0.2.10", "synthetic", None, parameters)
        self.api._addresses = {"boiler": "0x8", "controller": "0x35"}

        @asynccontextmanager
        async def session():
            yield self.session

        self.api.session = session
        self.api._disconnect = AsyncMock()
        self.definition = await self.api.discover(None)

    async def test_discovery_and_program_read_never_write(self):
        self.assertTrue(self.api.supports_schedule)
        self.assertTrue(self.api.supports_timed_modes)
        snapshot = await self.api.read_time_program(None, "heating", 1)
        self.assertEqual(snapshot.values[(1000, DAILY_IDS[0])], decode_day(ORIGINAL))
        self.assertEqual(len(snapshot.values), 8)
        self.assertEqual(self.session.writes, [])

    async def test_wrong_day_response_is_not_accepted(self):
        self.session.wrong_response = True
        with self.assertRaises(WolfError):
            await self.api.read_time_program(None, "heating", 1)

    async def test_day_write_confirm_and_exact_restore(self):
        result = await self.api.write_schedule_day(
            None, "heating", 1, "monday", WINDOWS, decode_day(ORIGINAL), lambda: False
        )
        self.assertIsNone(result[2].error)
        self.assertEqual(result[2].observed, result[1])
        self.assertEqual(len(self.session.writes), 1)
        windows = [w.as_dict() for w in parse_day(decode_day(ORIGINAL))]
        await self.api.write_schedule_day(
            None, "heating", 1, "monday", windows, result[1], lambda: False
        )
        self.assertEqual(self.session.days[("1", "0", "0", "1")], ORIGINAL)

    async def test_readonly_stale_editor_and_revocation_send_nothing(self):
        for expected, readonly in [
            (decode_day(ORIGINAL), True),
            ("00:00-00:00;" * 4 + "00:00-00:00", False),
        ]:
            with self.assertRaises(WolfError):
                await self.api.write_schedule_day(
                    None, "heating", 1, "monday", WINDOWS, expected, lambda: readonly
                )
        access = iter((False, True))
        with self.assertRaises(WolfError):
            await self.api.write_schedule_day(
                None,
                "heating",
                1,
                "monday",
                WINDOWS,
                decode_day(ORIGINAL),
                lambda: next(access),
            )
        self.assertEqual(self.session.writes, [])

    async def test_ack_does_not_confirm_no_second_write(self):
        self.session.update_day = False
        with patch(
            "custom_components.wolflink_local.local_programs.asyncio.sleep",
            new=AsyncMock(),
        ):
            _, _, outcome = await self.api.write_schedule_day(
                None,
                "heating",
                1,
                "monday",
                WINDOWS,
                decode_day(ORIGINAL),
                lambda: False,
            )
        self.assertEqual(outcome.error, "readback_mismatch")
        self.assertEqual(len(self.session.writes), 1)
        self.assertEqual(outcome.observed, decode_day(ORIGINAL))

    async def test_party_period_confirmed_before_activation_and_stop(self):
        progress = Mock()
        value = await self.api.set_timed_mode(
            None,
            "party",
            self.now,
            self.now + timedelta(minutes=15),
            lambda: self.now,
            lambda: False,
            progress=progress,
        )
        self.assertEqual(value, "1")
        self.assertEqual(len(self.session.writes), 2)
        self.assertEqual(set(self.session.writes[0][1]), {10151, 10152, 10153, 10154})
        self.assertEqual(self.session.writes[1], ("words", {10150: 1}))
        self.assertEqual(
            await self.api.set_timed_mode(
                None,
                "party",
                None,
                None,
                lambda: self.now,
                lambda: False,
                activate=False,
            ),
            "0",
        )

    async def test_holiday_period_preserves_party_and_scheduled_dates(self):
        start = self.now + timedelta(days=2)
        end = start + timedelta(days=5)
        value = await self.api.set_timed_mode(
            None, "holiday", start, end, lambda: self.now, lambda: False
        )
        self.assertEqual(value, "1")
        self.assertEqual(set(self.session.writes[0][1]), {10146, 10147, 10148, 10149})
        self.assertEqual(self.session.words[10150], 0)

    async def test_failed_period_ack_never_activates_even_if_values_were_written(self):
        self.session.fail_period = True
        with self.assertRaisesRegex(WolfError, "write_failed"):
            await self.api.set_timed_mode(
                None,
                "party",
                self.now,
                self.now + timedelta(minutes=15),
                lambda: self.now,
                lambda: False,
            )
        self.assertEqual(len(self.session.writes), 1)
        self.assertEqual(self.session.words[10150], 0)

    async def test_unconfirmed_period_never_activates(self):
        self.api._confirm_period = AsyncMock(return_value=False)
        with self.assertRaisesRegex(WolfError, "period_unconfirmed"):
            await self.api.set_timed_mode(
                None,
                "party",
                self.now,
                self.now + timedelta(minutes=15),
                lambda: self.now,
                lambda: False,
            )
        self.assertEqual(len(self.session.writes), 1)
        self.assertEqual(self.session.words[10150], 0)

    async def test_revoke_access_after_period_confirmation_blocks_activation(self):
        access = iter((False, False, True))
        with self.assertRaisesRegex(WolfError, "read_only"):
            await self.api.set_timed_mode(
                None,
                "party",
                self.now,
                self.now + timedelta(minutes=15),
                lambda: self.now,
                lambda: next(access),
            )
        self.assertEqual(len(self.session.writes), 1)
        self.assertEqual(self.session.words[10150], 0)

    async def test_later_actual_schedule_read_confirms_without_repeated_write(self):
        self.session.update_day = False
        with patch(
            "custom_components.wolflink_local.local_programs.asyncio.sleep",
            new=AsyncMock(),
        ):
            pid, target, _ = await self.api.write_schedule_day(
                None,
                "heating",
                1,
                "monday",
                WINDOWS,
                decode_day(ORIGINAL),
                lambda: False,
            )
        self.assertIn(pid, self.api._pending_days)
        self.session.days[("1", "0", "0", "1")] = encode_day(target, ORIGINAL)
        values = await self.api.read_extra_values(self.session)
        self.assertEqual(values[(1000, pid)], target)
        self.assertNotIn(pid, self.api._pending_days)
        self.assertEqual(len(self.session.writes), 1)

    async def test_period_readonly_clock_active_conflict_and_dst(self):
        for readonly, active, badclock in [
            (True, 0, False),
            (False, 1, False),
            (False, 0, True),
        ]:
            self.session.words[10145] = active
            self.session.words[10161] = (
                0 if badclock else encode_period_word("14:00", "time")
            )
            with self.assertRaises(WolfError):
                await self.api.set_timed_mode(
                    None,
                    "party",
                    self.now,
                    self.now + timedelta(minutes=15),
                    lambda: self.now,
                    lambda: readonly,
                )
        self.assertEqual(self.session.writes, [])
        ambiguous = datetime(2026, 10, 25, 2, 30, tzinfo=ZoneInfo("Europe/Berlin"))
        with self.assertRaises(WolfError):
            await self.api.set_timed_mode(
                None,
                "holiday",
                ambiguous,
                ambiguous + timedelta(days=1),
                lambda: self.now,
                lambda: False,
            )
