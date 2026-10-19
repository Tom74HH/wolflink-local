# SPDX-License-Identifier: GPL-3.0-only
"""ISM7 BM-2 day programs and periods, independently read back after every write.

Wire layouts cross-checked against smartset.net 4.4.5 converter/request models.
No vendor binaries are shipped. Source/protocol provenance: local/SOURCE.json.
"""

import asyncio
from datetime import datetime
import re
import struct
from time import monotonic
from xml.etree import ElementTree as ET

from .api import Snapshot, WriteOutcome, _MISSING
from .controls import BUNDLE
from .controls import DAILY_IDS, ParameterMeta, WolfError
from .time_program import WEEKDAYS, parameter_for, parse_day, preview_day, time_label
from .timed_modes import MODES, mode_metadata, period_values

PERIOD_TELEGRAMS = {
    33000000000: (10151, "time"),
    33000100000: (10152, "date"),
    33000200000: (10153, "time"),
    33000300000: (10154, "date"),
    33000600000: (10146, "time"),
    33000700000: (10147, "date"),
    33000800000: (10148, "time"),
    33000900000: (10149, "date"),
}


def day_attributes(pid, address):
    if pid not in DAILY_IDS:
        raise WolfError("not_allowed")
    index = DAILY_IDS.index(pid)
    return {
        "ba": address,
        "hp": str((index % 21) // 7 + 1),
        "ty": str(index // 21),
        "hk": "0",
        "d": str((index % 7 + 1) % 7),
    }


def decode_day(data):
    if not isinstance(data, bytes) or len(data) != 20:
        raise WolfError("invalid_schedule")
    labels = []
    for start, end in struct.iter_unpack("<HH", data):
        if (start, end) in ((0, 0), (65535, 65535)):
            labels.append("00:00-00:00")
        elif not 0 <= start < end <= 1440:
            raise WolfError("invalid_schedule")
        else:
            labels.append(f"{time_label(start)}-{time_label(end)}")
    result = ";".join(labels)
    parse_day(result)
    return result


def encode_day(target, original):
    """Change at most three windows; retain empty slot representation and tail."""
    windows = parse_day(target)
    existing = decode_day(original)
    if len(windows) > 3 or len(parse_day(existing)) > 3:
        raise WolfError("invalid_schedule")
    if any(window.end == 1440 for window in windows):
        # Vendor encoder clamps 24:00 to 23:59; never silently change user input.
        raise WolfError("local_midnight_unsupported")
    output = bytearray(original)
    for index in range(3):
        offset = index * 4
        if index < len(windows):
            output[offset : offset + 4] = struct.pack(
                "<HH", windows[index].start, windows[index].end
            )
        elif struct.unpack("<HH", original[offset : offset + 4]) not in (
            (0, 0),
            (65535, 65535),
        ):
            output[offset : offset + 4] = bytes(4)
    if parse_day(decode_day(bytes(output))) != windows:
        raise WolfError("invalid_schedule")
    return bytes(output)


def decode_period_word(word, kind):
    try:
        if kind == "time":
            hour, minute = word >> 8, word & 255
            if hour > 23 or minute > 59:
                raise ValueError()
            return f"{hour:02}:{minute:02}"
        day, month, year = (word & 31) + 1, ((word >> 5) & 15) + 1, 2000 + (word >> 9)
        if not 2000 <= year <= 2099:
            raise ValueError()
        return datetime(year, month, day).strftime("%d.%m.%Y")
    except ValueError:
        raise WolfError("invalid_period") from None


def encode_period_word(value, kind):
    try:
        if kind == "time":
            if not re.fullmatch(r"\d{2}:\d{2}", value):
                raise ValueError()
            hour, minute = map(int, value.split(":"))
            word = hour << 8 | minute
        else:
            parsed = datetime.strptime(value, "%d.%m.%Y")
            if not 2000 <= parsed.year <= 2099:
                raise ValueError()
            word = (
                (parsed.year - 2000) << 9 | (parsed.month - 1) << 5 | (parsed.day - 1)
            )
        if decode_period_word(word, kind) != value:
            raise ValueError()
        return word
    except (ValueError, TypeError):
        raise WolfError("invalid_period") from None


class LocalPrograms:
    supports_schedule = False
    supports_timed_modes = False

    async def _day_request(self, session, pid, *, data=None):
        attributes = day_attributes(pid, self._addresses["controller"])
        session.sequence += 1
        seq = str(session.sequence)
        request = ET.Element(
            "tbreq",
            bn=seq,
            gw="1",
            ae="true",
            ty="write" if data is not None else "pull",
        )
        row = {**attributes, "se": seq}
        if data is not None:
            if len(data) != 20:
                raise WolfError("invalid_schedule")
            row["db"] = data.hex().upper()
        ET.SubElement(request, "s03f3wr" if data is not None else "s03f1rd", row)
        response = await session.request(4, request)
        rows = response.findall("s03f3ac" if data is not None else "s03f2rs")
        if response.get("st") != "OK" or len(rows) != 1:
            raise WolfError(
                "write_failed" if data is not None else "schedule_unavailable"
            )
        reply = rows[0]
        if reply.get("st") != "OK" or any(
            reply.get(key, "").lower() != value.lower()
            for key, value in attributes.items()
        ):
            raise WolfError("malformed_response")
        if data is not None:
            # Acknowledgement is never treated as a newly read day value.
            return None
        text = reply.get("db", "")
        if not re.fullmatch(r"[0-9a-fA-F]{40}", text):
            raise WolfError("invalid_schedule")
        raw = bytes.fromhex(text)
        value = decode_day(raw)
        self._day_cache[pid] = (value, raw, monotonic())
        return value, raw

    async def _period_words(self, session):
        numbers = {number for number, _ in PERIOD_TELEGRAMS.values()}
        words = await session.telegrams(self._addresses["controller"], numbers)
        if set(words) != numbers:
            raise WolfError("period_unconfirmed")
        return {pid: words[number] for pid, (number, _) in PERIOD_TELEGRAMS.items()}

    async def discover_local_programs(self):
        self._day_cache = {}
        self._pending_days = getattr(self, "_pending_days", {})
        self.local_feature_errors = {}
        metadata = self._definition.metadata
        async with self._lock:
            try:
                async with self.session() as session:
                    await self._period_words(session)
                for pid, bundle, roles in MODES.values():
                    if pid not in {p.parameter_id for p in self._definition.sensors}:
                        continue
                    children = [
                        {
                            "Group": role,
                            "ParameterId": child,
                            "ValueId": child,
                            "ControlType": 9 if role.endswith("Date") else 10,
                            "IsReadOnly": False,
                            "NoDataPoint": False,
                        }
                        for role, child in roles.items()
                    ]
                    raw = {
                        "ControlType": 24,
                        "SubBundleId": bundle,
                        "IsReadOnly": False,
                        "NoDataPoint": False,
                        "ListItems": [{"Value": 0}, {"Value": 1}],
                        "ChildParameterDescriptors": children,
                    }
                    metadata[pid] = ParameterMeta(
                        pid,
                        pid,
                        BUNDLE,
                        "Partymodus" if bundle == 3500 else "Urlaubsmodus",
                        raw,
                    )
                self.supports_timed_modes = all(
                    pid in metadata for pid, _, _ in MODES.values()
                )
            except WolfError as exc:
                self.supports_timed_modes = False
                self.local_feature_errors["periods"] = exc.code
            try:
                async with self.session() as session:
                    await self._day_request(session, DAILY_IDS[0])
                self.supports_schedule = True
                for pid in DAILY_IDS:
                    metadata[pid] = ParameterMeta(
                        pid,
                        pid,
                        BUNDLE,
                        "Zeitfenster",
                        {"ControlType": 14, "IsReadOnly": False, "NoDataPoint": False},
                    )
            except WolfError as exc:
                self.supports_schedule = False
                self.local_feature_errors["schedule"] = exc.code

    async def read_extra_values(self, session):
        for pid, (target, deadline) in list(self._pending_days.items()):
            value, _ = await self._day_request(session, pid)
            if parse_day(value) == parse_day(target) or monotonic() >= deadline:
                self._pending_days.pop(pid, None)
        return {
            (BUNDLE, pid): value
            for pid, (value, _, stamp) in self._day_cache.items()
            if monotonic() - stamp < 60
        }

    async def read_time_program(self, device, area, program):
        if not self.supports_schedule:
            raise WolfError("schedule_unavailable")
        async with self._lock, self.session() as session:
            values = {}
            for weekday in WEEKDAYS:
                pid = parameter_for(area, program, weekday)
                value, _ = await self._day_request(session, pid)
                values[(BUNDLE, pid)] = value
            active = 34001600000 if area == "heating" else 35000400000
            values.update(
                {
                    (BUNDLE, pid): value
                    for pid, value in (
                        await self._read_values(session, [active])
                    ).items()
                }
            )
            return Snapshot(values)

    async def write_schedule_day(
        self,
        device,
        area,
        program,
        weekday,
        windows,
        expected,
        read_only,
        *,
        progress=None,
    ):
        draft = preview_day(area, program, weekday, windows)
        pid, target = draft["parameter_id"], draft["serialized_preview"]
        parse_day(expected)
        async with self._lock:
            if read_only():
                raise WolfError("read_only")
            if not self.supports_schedule or pid not in self._definition.metadata:
                raise WolfError("not_allowed")
            async with self.session() as session:
                current, raw = await self._day_request(session, pid)
                if parse_day(current) != parse_day(expected):
                    raise WolfError("schedule_conflict")
                if parse_day(current) == parse_day(target):
                    return (
                        pid,
                        target,
                        WriteOutcome(self._definition.metadata, observed=current),
                    )
                data = encode_day(target, raw)
                if read_only():
                    raise WolfError("read_only")
                try:
                    await self._day_request(session, pid, data=data)
                except Exception:
                    # A transport failure might follow a completed write. Only read.
                    await self._disconnect()
            if progress:
                progress("awaiting_confirmation")
            outcome = WriteOutcome(self._definition.metadata)
            for delay in (0, 1, 2, 3, 5):
                if delay:
                    await asyncio.sleep(delay)
                outcome.observed = _MISSING
                try:
                    async with self.session() as session:
                        outcome.observed, _ = await self._day_request(session, pid)
                    if parse_day(outcome.observed) == parse_day(target):
                        return pid, target, outcome
                except WolfError:
                    pass
            self._pending_days[pid] = (target, monotonic() + 600)
            outcome.error = (
                "readback_mismatch" if outcome.has_observed_value else "readback_failed"
            )
            return pid, target, outcome

    async def _write_period_rows(self, session, rows, read_only):
        if read_only():
            raise WolfError("read_only")
        session.sequence += 1
        request = ET.Element(
            "tbreq", bn=str(session.sequence), gw="1", ae="true", ty="write"
        )
        address = self._addresses["controller"]
        for number, word in rows.items():
            ET.SubElement(
                request,
                "iwr",
                {
                    "se": str(number),
                    "ba": address,
                    "in": str(number),
                    "dl": hex(word & 255),
                    "dh": hex(word >> 8),
                },
            )
        response = await session.request(4, request)
        replies = response.findall("iac")
        if (
            response.get("st") != "OK"
            or len(replies) != len(rows)
            or {r.get("in") for r in replies} != {str(n) for n in rows}
            or any(r.get("st") != "OK" for r in replies)
        ):
            raise WolfError("write_failed")

    async def _confirm_period(self, expected, flag=None):
        for delay in (0, 1, 2, 3, 5):
            if delay:
                await asyncio.sleep(delay)
            try:
                async with self.session() as session:
                    words = await self._period_words(session) if expected else {}
                    flags = await self._read_values(session, [flag[0]]) if flag else {}
                if all(words.get(pid) == value for pid, value in expected.items()) and (
                    flag is None or flags.get(flag[0]) == flag[1]
                ):
                    return True
            except WolfError:
                pass
        return False

    async def set_timed_mode(
        self, device, mode, start, end, now, read_only, *, activate=True, progress=None
    ):
        if mode not in MODES or type(activate) is not bool:
            raise WolfError("not_allowed")
        expected_values = period_values(start, end, now()) if activate else {}
        if activate and mode == "party":
            minutes = (end.timestamp() - start.timestamp()) / 60
            if not 15 <= minutes <= 1440 or minutes % 15:
                raise WolfError("invalid_period")
        async with self._lock:
            if read_only():
                raise WolfError("read_only")
            if not self.supports_timed_modes:
                raise WolfError("local_feature_unavailable")
            pid, _, roles = mode_metadata(mode, self._definition.metadata)
            expected = {
                roles[role]: encode_period_word(value, PERIOD_TELEGRAMS[roles[role]][1])
                for role, value in expected_values.items()
            }
            period_send_failed = False
            async with self.session() as session:
                flags = await self._read_values(
                    session, [item[0] for item in MODES.values()]
                )
                if any(flags.get(item[0]) not in (0, 1) for item in MODES.values()):
                    raise WolfError("readback_failed")
                if activate and any(flags[item[0]] != 0 for item in MODES.values()):
                    raise WolfError("mode_already_active")
                if not activate and flags[pid] == 0:
                    return "0"
                if activate:
                    await self._period_words(session)
                    clock = await session.telegrams(
                        self._addresses["controller"], {10160, 10161}
                    )
                    if set(clock) != {10160, 10161}:
                        raise WolfError("local_clock_mismatch")
                    stamp = datetime.strptime(
                        decode_period_word(clock[10160], "date")
                        + " "
                        + decode_period_word(clock[10161], "time"),
                        "%d.%m.%Y %H:%M",
                    )
                    if abs((stamp - now().replace(tzinfo=None)).total_seconds()) > 300:
                        raise WolfError("local_clock_mismatch")
                    try:
                        await self._write_period_rows(
                            session,
                            {
                                PERIOD_TELEGRAMS[child][0]: word
                                for child, word in expected.items()
                            },
                            read_only,
                        )
                    except WolfError as exc:
                        if exc.code == "read_only":
                            raise
                        period_send_failed = True
                        await self._disconnect()
                    except Exception:
                        period_send_failed = True
                        await self._disconnect()
            if activate:
                if progress:
                    progress("awaiting_period_confirmation")
                period_confirmed = await self._confirm_period(expected)
                if period_send_failed:
                    raise WolfError("write_failed")
                if not period_confirmed:
                    raise WolfError("period_unconfirmed")
                period_values(start, end, now())
                # Recheck both flags just before activation; never merge opposing modes.
                async with self.session() as session:
                    flags = await self._read_values(
                        session, [item[0] for item in MODES.values()]
                    )
                    if any(flags.get(item[0]) != 0 for item in MODES.values()):
                        raise WolfError("mode_already_active")
            if progress:
                progress("sending")
            async with self.session() as session:
                try:
                    await self._write_period_rows(
                        session,
                        {self.parameters[pid]["telegrams"][0]: int(activate)},
                        read_only,
                    )
                except WolfError as exc:
                    if exc.code == "read_only":
                        raise
                    await self._disconnect()
                except Exception:
                    await self._disconnect()
            if progress:
                progress("awaiting_confirmation")
            if not await self._confirm_period(expected, (pid, int(activate))):
                raise WolfError("readback_failed")
            return str(int(activate))
