# SPDX-License-Identifier: GPL-3.0-only
# Protocol and conversions adapted from zivillian/ism7mqtt; see local/SOURCE.json.
"""Native ISM7 TLS transport. No MQTT, portal calls, or replayed writes.

Protocol reference: https://github.com/zivillian/ism7mqtt/blob/master/PROTOCOL.md
The backend supports the CGB-2/BM-2 family. Optional schedules and timed-mode
periods are implemented by LocalPrograms and gated by successful read probes.
"""

import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
import hashlib
import ipaddress
import json
from pathlib import Path
import ssl
import struct
from xml.etree import ElementTree as ET

from . import models

from .api import Definition, Snapshot, WriteOutcome, _MISSING
from .local_programs import LocalPrograms
from .controls import (
    BUNDLE,
    CONTROLS,
    ParameterMeta,
    WolfError,
    decimal_value,
    validate_write,
)

ASSETS = Path(__file__).parent / "local"
MAX_FRAME = 2_000_000


def valid_host(host):
    """Accept a literal local address; never send the module password to a URL."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise WolfError("cannot_connect") from None
    if (
        not address.is_private
        or address.is_loopback
        or address.is_unspecified
        or address.is_multicast
    ):
        raise WolfError("cannot_connect")
    return str(address)


def make_context():
    """Use ISM7 legacy TLS only for this socket, with application-level pinning."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.options |= ssl.OP_LEGACY_SERVER_CONNECT
    context.set_ciphers("AES256-SHA256:@SECLEVEL=0")
    context.load_cert_chain(ASSETS / "client-cert.pem", ASSETS / "client-key.pem")
    return context


def decode_parameter(spec, words):
    numbers = spec["telegrams"]
    if any(number not in words for number in numbers):
        return None
    raw = words[numbers[0]]
    if spec["type"].startswith("SS") and raw == 0x8000:
        return None
    if spec["converter"] == "NumericConverter32Template":
        raw |= words[numbers[1]] << 16
    if spec.get("bit") is not None:
        return (raw >> int(spec["bit"])) & 1
    kind = spec["type"]
    if kind.startswith("SS") and raw >= 32768:
        raw -= 65536
    divisor = {"SS10": 10, "US10": 10, "SS100": 100, "US4": 4, "IntDiv60": 60}.get(
        kind, 1
    )
    return raw / divisor if divisor != 1 else raw


class Session:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.sequence = 0

    async def request(self, kind, element):
        payload = ET.tostring(element, encoding="utf-8", xml_declaration=True)
        self.writer.write(struct.pack(">Ih", len(payload), kind) + payload)
        await self.writer.drain()
        header = await self.reader.readexactly(6)
        length, response_kind = struct.unpack(">Ih", header)
        if length > MAX_FRAME:
            raise WolfError("malformed_response")
        data = await self.reader.readexactly(length)
        if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
            raise WolfError("malformed_response")
        result = ET.fromstring(data)
        expected = {
            8: (9, "direct-logon-response"),
            2: (3, "read-systemconfig-response"),
            4: (5, "tbres"),
        }
        if (response_kind, result.tag) != expected[kind]:
            raise WolfError("malformed_response")
        if kind == 4 and result.get("bn") != element.get("bn"):
            raise WolfError("malformed_response")
        return result

    async def telegrams(self, address, numbers):
        self.sequence += 1
        request = ET.Element(
            "tbreq", bn=str(self.sequence), gw="1", ae="false", ty="pull"
        )
        for number in sorted(set(numbers)):
            ET.SubElement(
                request, "ird", {"se": str(number), "ba": address, "in": str(number)}
            )
        response = await self.request(4, request)
        words = {}
        for row in response.findall("irs"):
            number = int(row.get("in", "-1"))
            if (
                number not in numbers
                or row.get("st") != "OK"
                or row.get("ba", address).lower() != address.lower()
            ):
                continue
            low, high = int(row.get("dl", "-1"), 0), int(row.get("dh", "-1"), 0)
            if not (0 <= low <= 255 and 0 <= high <= 255) or number in words:
                raise WolfError("malformed_response")
            words[number] = low | high << 8
        return words

    async def write_word(self, address, number, word):
        self.sequence += 1
        request = ET.Element(
            "tbreq", bn=str(self.sequence), gw="1", ae="true", ty="write"
        )
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
        response = await self.request(4, request)
        rows = response.findall("iac")
        if (
            response.get("st") != "OK"
            or len(rows) != 1
            or rows[0].get("st") != "OK"
            or rows[0].get("in") != str(number)
        ):
            raise WolfError("write_failed")


class LocalWolfApi(LocalPrograms):
    """One configured local module, serialized traffic and one kept-alive connection."""

    supports_schedule = False

    def __init__(
        self,
        host,
        password,
        context,
        parameters,
        fingerprint=None,
        module_identity=None,
    ):
        self.host = valid_host(host)
        self._password = password
        self._context = context
        self.parameters = {int(pid): spec for pid, spec in parameters.items()}
        self.fingerprint = fingerprint
        self.module_identity = module_identity
        self._lock = asyncio.Lock()
        self._addresses = {}
        self._device = None
        self._session = None
        self._keepalive_task = None
        self._definition = None
        self.schedule_acknowledgements = {}
        self._day_cache = {}
        self._pending_days = {}

    @classmethod
    async def create(cls, hass, host, password, fingerprint=None, module_identity=None):
        def assets():
            return make_context(), json.loads(
                (ASSETS / "parameters.json").read_text(encoding="utf8")
            )

        context, parameters = await hass.async_add_executor_job(assets)
        return cls(host, password, context, parameters, fingerprint, module_identity)

    @asynccontextmanager
    async def session(self):
        writer = None
        failed = True
        try:
            async with asyncio.timeout(45):
                if self._session is None:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(
                            self.host,
                            9092,
                            ssl=self._context,
                            server_hostname="ism7.server",
                            ssl_handshake_timeout=10,
                        ),
                        12,
                    )
                    peer = writer.get_extra_info("ssl_object").getpeercert(
                        binary_form=True
                    )
                    fingerprint = hashlib.sha256(peer).hexdigest()
                    if self.fingerprint is not None and fingerprint != self.fingerprint:
                        raise WolfError("local_certificate_changed")
                    session = Session(reader, writer)
                    login = ET.Element("direct-logon-request")
                    ET.SubElement(login, "password").text = self._password
                    response = await session.request(8, login)
                    # Only explicit credential rejection needs a HA reauth flow.
                    # Busy/pending/error are transient: disconnect, then let HA's
                    # normal retry reconnect with the stored password. No replay.
                    if response.get("state") == "invalidCredentials":
                        raise WolfError("invalid_auth")
                    if response.get("state") in ("busy", "pending", "error"):
                        raise WolfError("cannot_connect")
                    if response.get("state") != "ok":
                        raise WolfError("malformed_response")
                    self.fingerprint = fingerprint
                    session.sid = response.get("sid", "")
                    session.serial = response.findtext("serialnumber")
                    if not session.serial:
                        raise WolfError("malformed_response")
                    identity = int(
                        hashlib.sha256(session.serial.encode()).hexdigest()[:12], 16
                    )
                    if (
                        self.module_identity is not None
                        and identity != self.module_identity
                    ):
                        raise WolfError("local_certificate_changed")
                    self.module_identity = identity
                    self._session = session
                    if self._keepalive_task is None:
                        self._keepalive_task = asyncio.create_task(self._keepalive())
                yield self._session
                failed = False
        except WolfError:
            raise
        except (OSError, TimeoutError, asyncio.IncompleteReadError):
            raise WolfError("cannot_connect") from None
        except (ValueError, ET.ParseError, KeyError, TypeError):
            raise WolfError("malformed_response") from None
        finally:
            if failed:
                if writer is not None and self._session is None:
                    writer.close()
                await self._disconnect()

    async def _disconnect(self):
        session, self._session = self._session, None
        if session is not None:
            session.writer.close()
            try:
                await asyncio.wait_for(session.writer.wait_closed(), 2)
            except (OSError, TimeoutError):
                pass

    async def _keepalive(self):
        sequence = 0
        while True:
            await asyncio.sleep(25)
            async with self._lock:
                if self._session is None:
                    continue
                try:
                    async with asyncio.timeout(10):
                        sequence = (sequence + 1) % 32768
                        session = self._session
                        session.writer.write(struct.pack(">Ihh", 2, 15, sequence))
                        await session.writer.drain()
                        header = await session.reader.readexactly(6)
                        length, kind = struct.unpack(">Ih", header)
                        if length != 2 or kind != 15:
                            raise WolfError("malformed_response")
                        if await session.reader.readexactly(2) != struct.pack(
                            ">h", sequence
                        ):
                            raise WolfError("malformed_response")
                except (WolfError, OSError, TimeoutError, asyncio.IncompleteReadError):
                    await self._disconnect()

    async def systems(self):
        async with self._lock, self.session() as session:
            result = await session.request(
                2, ET.Element("read-systemconfig-request", sid=session.sid)
            )
            devices = result.findall(".//busDevice")
            for did, key in ((0x21, "boiler"), (0x20, "controller")):
                matches = [d for d in devices if int(d.get("did", "0"), 0) == did]
                if len(matches) != 1:
                    raise WolfError("local_unsupported_system")
                self._addresses[key] = matches[0].get("ba")
            # Module identity is independent of its DHCP address. Never put it in logs.
            if not session.serial:
                raise WolfError("malformed_response")
            identifier = int(
                hashlib.sha256(session.serial.encode()).hexdigest()[:12], 16
            )
            self._device = models.Device(identifier, identifier, "WOLF Lokal (ISM7)")
            return [self._device]

    def address(self, pid):
        return self._addresses[
            "boiler" if pid // 100000 // 1000 == 180 else "controller"
        ]

    async def _read_values(self, session, ids):
        words = {}
        for address in sorted({self.address(pid) for pid in ids}):
            requested = {
                number
                for pid in ids
                if self.address(pid) == address
                for number in self.parameters[pid]["telegrams"]
            }
            words[address] = await session.telegrams(address, requested)
        return {
            pid: value
            for pid in ids
            if (
                value := decode_parameter(
                    self.parameters[pid], words[self.address(pid)]
                )
            )
            is not None
        }

    async def discover(self, device):
        async with self._lock, self.session() as session:
            values = await self._read_values(session, self.parameters)
        sensors, metadata = [], {}
        types = {
            "°C": models.Temperature,
            "bar": models.Pressure,
            "%": models.PercentageParameter,
            "h": models.HoursParameter,
            "l/min": models.FlowParameter,
            "kWh": models.EnergyParameter,
        }
        for pid, spec in self.parameters.items():
            if pid not in values:
                continue
            args = dict(
                value_id=pid,
                name=spec["name"],
                parent="ISM7",
                parameter_id=pid,
                bundle_id=BUNDLE,
                read_only=True,
            )
            if spec.get("items"):
                sensor = models.ListItemParameter(
                    items=[
                        models.ListItem(int(code), label)
                        for code, label in spec["items"].items()
                    ],
                    **args,
                )
            else:
                sensor = types.get(spec.get("unit"), models.SimpleParameter)(**args)
            sensors.append(sensor)
            if pid in CONTROLS:
                control = CONTROLS[pid]
                raw = {
                    "IsReadOnly": False,
                    "NoDataPoint": False,
                    "ControlType": control.control_type,
                    "Unit": control.unit,
                }
                if control.options:
                    raw["ListItems"] = [{"Value": code} for code, _ in control.options]
                else:
                    raw.update(
                        MinValue=str(control.minimum),
                        MaxValue=str(control.maximum),
                        StepWidth=str(control.step),
                    )
                metadata[pid] = ParameterMeta(pid, pid, BUNDLE, spec["name"], raw)
        self._definition = Definition(sensors, metadata)
        await self.discover_local_programs()
        return self._definition

    async def read(self, device, definition):
        async with self._lock, self.session() as session:
            values = await self._read_values(session, self.parameters)
            return Snapshot(
                {
                    **{(BUNDLE, pid): value for pid, value in values.items()},
                    **await self.read_extra_values(session),
                }
            )

    async def write(self, device, parameter_id, value, read_only, *, progress=None):
        async with self._lock:
            if read_only():
                raise WolfError("read_only")
            if (
                self._definition is None
                or parameter_id not in self._definition.metadata
            ):
                raise WolfError("not_allowed")
            meta = self._definition.metadata[parameter_id]
            target = validate_write(parameter_id, value, meta)
            spec = self.parameters[parameter_id]
            if (
                spec["converter"] != "NumericConverter16Template"
                or len(spec["telegrams"]) != 1
            ):
                raise WolfError("not_allowed")
            factor = 10 if spec["type"] == "SS10" else 1
            word = int(Decimal(str(target)) * factor) & 65535
            outcome = WriteOutcome(self._definition.metadata)
            async with self.session() as session:
                before = await self._read_values(session, [parameter_id])
                if parameter_id not in before:
                    raise WolfError("readback_failed")
                if decimal_value(before[parameter_id]) == Decimal(str(target)):
                    outcome.observed = before[parameter_id]
                    return outcome
                # BM-2 reports 13 when the relevant operating mode disallows changes.
                guard = (
                    34000400000
                    if parameter_id // 100000 // 1000 == 340
                    else 35000100000
                )
                guards = await self._read_values(session, [guard])
                if guards.get(guard) in (None, 13):
                    raise WolfError("not_writable")
                if read_only():
                    raise WolfError("read_only")
                try:
                    await session.write_word(
                        self.address(parameter_id), spec["telegrams"][0], word
                    )
                except Exception:
                    # The request may have reached the heater. Never resend it.
                    outcome.error = "write_failed"
                    await self._disconnect()
                if progress:
                    progress("awaiting_confirmation")
            for delay in (0, 1, 2, 3, 5):
                if delay:
                    await asyncio.sleep(delay)
                outcome.observed = _MISSING
                try:
                    async with self.session() as session:
                        observed = await self._read_values(session, [parameter_id])
                    if parameter_id in observed:
                        outcome.observed = observed[parameter_id]
                        if decimal_value(outcome.observed) == Decimal(str(target)):
                            outcome.error = None
                            return outcome
                except WolfError:
                    pass
            outcome.error = (
                "readback_mismatch" if outcome.has_observed_value else "readback_failed"
            )
            return outcome

    async def aclose(self):
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
            self._keepalive_task = None
        await self._disconnect()
        self._password = ""
