"""Native ISM7 protocol, validation and write-confirmation tests, no heater writes."""

import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import struct
from types import SimpleNamespace as NS
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock, patch
from xml.etree import ElementTree as ET

from custom_components.wolflink_local.local_api import (
    LocalWolfApi,
    Session,
    decode_parameter,
    valid_host,
)
from custom_components.wolflink_local.controls import WolfError


class ConversionTests(TestCase):
    def test_private_host_only(self):
        self.assertEqual(valid_host("192.0.2.10"), "192.0.2.10")
        for host in (
            "https://example.com",
            "8.8.8.8",
            "127.0.0.1",
            "0.0.0.0",
            "224.1.1.1",
        ):
            with self.subTest(host=host), self.assertRaises(WolfError):
                valid_host(host)

    def test_scales_signed_missing_and_bit_values(self):
        spec = {
            "telegrams": [1],
            "converter": "NumericConverter16Template",
            "type": "SS10",
        }
        self.assertEqual(decode_parameter(spec, {1: 65501}), -3.5)
        self.assertIsNone(decode_parameter(spec, {1: 32768}))
        self.assertIsNone(decode_parameter(spec, {}))
        self.assertEqual(decode_parameter({**spec, "type": "SS100"}, {1: 161}), 1.61)
        self.assertEqual(
            decode_parameter({**spec, "type": "US", "bit": "3"}, {1: 8}), 1
        )
        self.assertEqual(
            decode_parameter(
                {
                    **spec,
                    "type": "UINT32",
                    "converter": "NumericConverter32Template",
                    "telegrams": [1, 2],
                },
                {1: 3, 2: 2},
            ),
            131075,
        )


class ProtocolTests(IsolatedAsyncioTestCase):
    def session(self, kind, payload):
        reader = asyncio.StreamReader()
        reader.feed_data(struct.pack(">Ih", len(payload), kind) + payload)
        reader.feed_eof()
        return Session(reader, NS(write=Mock(), drain=AsyncMock()))

    async def test_frame_correspondence_size_and_xml_validation(self):
        for kind, payload in (
            (3, b'<tbres bn="1"/>'),
            (5, b'<tbres bn="2"/>'),
            (5, b'<!DOCTYPE a [<!ENTITY x "foo">]><tbres bn="1"/>'),
        ):
            with self.subTest(payload=payload), self.assertRaises(WolfError):
                await self.session(kind, payload).request(
                    4, ET.Element("tbreq", bn="1")
                )
        reader = asyncio.StreamReader()
        reader.feed_data(struct.pack(">Ih", 2000001, 5))
        with self.assertRaises(WolfError):
            await Session(reader, NS(write=Mock(), drain=AsyncMock())).request(
                4, ET.Element("tbreq", bn="1")
            )

    async def test_actual_telegram_and_write_ack_validation(self):
        session = self.session(
            5,
            b'<tbres bn="1" st="OK"><irs ba="0x8" in="13" dl="0x95" dh="0x1" st="OK"/></tbres>',
        )
        self.assertEqual(await session.telegrams("0x8", {13}), {13: 405})
        self.assertEqual(
            struct.unpack(">Ih", session.writer.write.call_args.args[0][:6])[1], 4
        )
        session = self.session(
            5, b'<tbres bn="1" st="OK"><iac in="999" st="OK"/></tbres>'
        )
        with self.assertRaises(WolfError):
            await session.write_word("0x35", 19, 600)

    async def test_invalid_and_duplicate_words_rejected(self):
        for rows in (
            b'<irs in="13" dl="0x100" dh="0" st="OK"/>',
            b'<irs in="13" dl="1" dh="0" st="OK"/><irs in="13" dl="2" dh="0" st="OK"/>',
        ):
            with self.assertRaises(WolfError):
                await self.session(5, b'<tbres bn="1">' + rows + b"</tbres>").telegrams(
                    "0x8", {13}
                )


class BackendTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        parameters = json.loads(
            Path("custom_components/wolflink_local/local/parameters.json").read_text(
                encoding="utf8"
            )
        )
        self.api = LocalWolfApi(
            "192.0.2.10", "synthetic-password", None, parameters, "synthetic-pin"
        )
        self.api._addresses = {"boiler": "0x8", "controller": "0x35"}
        self.session = NS(write_word=AsyncMock())

        @asynccontextmanager
        async def session():
            yield self.session

        self.api.session = session
        self.values = {pid: 1 for pid in self.api.parameters}
        self.values.update({35000900000: 60, 34002600000: 4, 34003500000: 20})

        async def values(session, ids):
            return {pid: self.values[pid] for pid in ids if pid in self.values}

        self.api._read_values = AsyncMock(side_effect=values)
        self.api.discover_local_programs = AsyncMock()
        self.definition = await self.api.discover(None)

    async def test_discovery_and_read_never_write(self):
        self.assertEqual(len(self.definition.metadata), 8)
        self.assertNotIn(22003400000, self.definition.metadata)
        snapshot = await self.api.read(None, self.definition)
        self.assertEqual(snapshot.values[(1000, 35000900000)], 60)
        self.session.write_word.assert_not_called()

    async def test_readonly_validation_and_revocation(self):
        for pid, value, readonly in (
            (35000900000, 61, True),
            (35000900000, 99, False),
            (34002900000, 9, False),
            (34002600000, 1.2, False),
            (34003200000, 1, False),
        ):
            with self.subTest(pid=pid, value=value), self.assertRaises(WolfError):
                await self.api.write(None, pid, value, lambda: readonly)
        self.session.write_word.assert_not_called()
        access = iter((False, True))
        with self.assertRaises(WolfError):
            await self.api.write(None, 35000900000, 61, lambda: next(access))
        self.session.write_word.assert_not_called()

    async def test_single_write_confirmed_by_actual_read(self):
        async def write(*args):
            self.values[35000900000] = 61

        self.session.write_word.side_effect = write
        progress = Mock()
        outcome = await self.api.write(
            None, 35000900000, 61, lambda: False, progress=progress
        )
        self.session.write_word.assert_awaited_once_with("0x35", 19, 610)
        self.assertEqual(outcome.observed, 61)
        self.assertIsNone(outcome.error)
        progress.assert_called_once_with("awaiting_confirmation")

    async def test_ack_is_not_actual_state_and_write_never_replayed(self):
        with patch(
            "custom_components.wolflink_local.local_api.asyncio.sleep", new=AsyncMock()
        ):
            outcome = await self.api.write(None, 35000900000, 61, lambda: False)
        self.assertEqual(outcome.error, "readback_mismatch")
        self.assertEqual(outcome.observed, 60)
        self.session.write_word.assert_awaited_once()

    async def test_uncertain_send_readback_can_confirm_without_second_write(self):
        async def write(*args):
            self.values[35000900000] = 61
            raise TimeoutError()

        self.session.write_word.side_effect = write
        outcome = await self.api.write(None, 35000900000, 61, lambda: False)
        self.assertEqual(outcome.observed, 61)
        self.assertIsNone(outcome.error)
        self.session.write_word.assert_awaited_once()

    async def test_already_requested_state_no_write_and_unavailable_features(self):
        outcome = await self.api.write(None, 35000900000, 60, lambda: False)
        self.assertIsNone(outcome.error)
        self.session.write_word.assert_not_called()

    async def test_guard_block_and_same_module_serialization(self):
        self.values[35000100000] = 13
        with self.assertRaises(WolfError):
            await self.api.write(None, 35000900000, 61, lambda: False)
        self.session.write_word.assert_not_called()
        self.values[35000100000] = 1
        order = []

        async def write(address, number, word):
            order.append("start")
            await asyncio.sleep(0)
            self.values[35000900000] = word / 10
            order.append("end")

        self.session.write_word.side_effect = write
        await asyncio.gather(
            self.api.write(None, 35000900000, 61, lambda: False),
            self.api.write(None, 35000900000, 62, lambda: False),
        )
        self.assertEqual(order, ["start", "end", "start", "end"])


class AuthenticationTests(IsolatedAsyncioTestCase):
    async def test_next_poll_reconnects_with_stored_password_after_busy(self):
        api = LocalWolfApi("192.0.2.10", "synthetic-password", None, {})
        def writer():
            return NS(get_extra_info=Mock(return_value=NS(getpeercert=Mock(return_value=b"peer"))),close=Mock(),wait_closed=AsyncMock())
        first, second = writer(), writer()
        successful = ET.fromstring('<direct-logon-response state="ok" sid="new-session"><serialnumber>synthetic-module</serialnumber></direct-logon-response>')
        request = AsyncMock(side_effect=[ET.Element("direct-logon-response",state="busy"), successful])
        with patch("custom_components.wolflink_local.local_api.asyncio.open_connection",new=AsyncMock(side_effect=[(Mock(),first),(Mock(),second)])),patch.object(Session,"request",new=request):
            with self.assertRaisesRegex(WolfError,"cannot_connect"):
                async with api.session():
                    pass
            async with api.session() as session:
                self.assertEqual(session.sid,"new-session")
            for call in request.call_args_list:
                self.assertEqual(call.args[1].findtext("password"),"synthetic-password")
        await api.aclose()

    async def test_busy_pending_and_error_do_not_request_reauthentication(self):
        for state, expected in [("busy", "cannot_connect"), ("pending", "cannot_connect"), ("error", "cannot_connect"), ("invalidCredentials", "invalid_auth"), ("unexpected", "malformed_response")]:
            with self.subTest(state=state):
                api = LocalWolfApi("192.0.2.10", "synthetic-password", None, {})
                writer = NS(get_extra_info=Mock(return_value=NS(getpeercert=Mock(return_value=b"peer"))), close=Mock())
                with patch("custom_components.wolflink_local.local_api.asyncio.open_connection",new=AsyncMock(return_value=(Mock(), writer))), patch.object(Session, "request", new=AsyncMock(return_value=ET.Element("direct-logon-response",state=state))):
                    with self.assertRaisesRegex(WolfError, "^"+expected+"$"):
                        async with api.session():
                            self.fail("Rejected session was used")
                self.assertIsNone(api._session)
                writer.close.assert_called_once()

    async def test_certificate_change_is_blocked_before_password_and_socket_closed(
        self,
    ):
        api = LocalWolfApi("192.0.2.10", "synthetic-password", None, {}, "wrong-pin")
        reader = asyncio.StreamReader()
        writer = NS(
            get_extra_info=Mock(
                return_value=NS(getpeercert=Mock(return_value=b"peer"))
            ),
            close=Mock(),
            write=Mock(),
            wait_closed=AsyncMock(),
        )
        with patch(
            "custom_components.wolflink_local.local_api.asyncio.open_connection",
            new=AsyncMock(return_value=(reader, writer)),
        ):
            with self.assertRaisesRegex(WolfError, "local_certificate_changed"):
                async with api.session():
                    pass
        writer.write.assert_not_called()
        writer.close.assert_called_once()

    async def test_connection_loss_clears_session_and_secrets_are_not_exception_text(
        self,
    ):
        api = LocalWolfApi("192.0.2.10", "synthetic-password", None, {})
        with patch(
            "custom_components.wolflink_local.local_api.asyncio.open_connection",
            new=AsyncMock(side_effect=OSError("synthetic-password")),
        ):
            with self.assertRaisesRegex(WolfError, "^cannot_connect$"):
                async with api.session():
                    pass
        self.assertIsNone(api._session)
        await api.aclose()
        self.assertEqual(api._password, "")


class FlowTests(IsolatedAsyncioTestCase):
    async def test_local_flow_stores_pin_and_enforces_initial_readonly(self):
        from custom_components.wolflink_local.config_flow import WolfLinkConfigFlow

        flow = WolfLinkConfigFlow()
        flow.hass = Mock()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = Mock()
        api = NS(
            host="192.0.2.10",
            fingerprint="synthetic-pin",
            systems=AsyncMock(return_value=[NS(id=42)]),
            aclose=AsyncMock(),
        )
        with patch(
            "custom_components.wolflink_local.config_flow.LocalWolfApi.create",
            new=AsyncMock(return_value=api),
        ):
            result = await flow.async_step_local(
                {"host": "192.0.2.10", "password": "synthetic-password"}
            )
        self.assertEqual(result["step_id"], "local_confirm")
        result = await flow.async_step_local_confirm({})
        self.assertEqual(result["data"]["connection_type"], "local")
        self.assertEqual(result["data"]["fingerprint"], "synthetic-pin")
        self.assertEqual(result["data"]["module_identity"], 42)
        self.assertEqual(result["options"], {"read_only": True})
        api.aclose.assert_awaited_once()
