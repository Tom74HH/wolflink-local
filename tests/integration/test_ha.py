"""Tests against real Home Assistant classes, without starting a live HA server."""

import importlib.util
import asyncio
import json
from pathlib import Path
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

if importlib.util.find_spec("homeassistant") is None:
    raise unittest.SkipTest(
        "Requires Home Assistant 2026.10.1; API tests run independently"
    )

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from custom_components.wolflink_local.models import Device, Temperature, ListItemParameter, ListItem

from custom_components.wolflink_local import (
    Runtime,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.wolflink_local.api import Definition, Snapshot, WriteOutcome
from custom_components.wolflink_local.const import DOMAIN
from custom_components.wolflink_local.controls import (
    CONTROLS,
    ParameterMeta,
    WolfError,
)
from custom_components.wolflink_local.coordinator import WolfLinkCoordinator
from custom_components.wolflink_local.config_flow import (
    WolfLinkConfigFlow,
    WolfLinkOptionsFlow,
)
from custom_components.wolflink_local.select import WolfSelect
from custom_components.wolflink_local.number import WolfNumber
from custom_components.wolflink_local.sensor import WolfLinkSensor, SENSOR_DESCRIPTIONS
from custom_components.wolflink_local.future import DailyScheduleSensor
from custom_components.wolflink_local.diagnostics import (
    async_get_config_entry_diagnostics,
)
from .test_controls import raw_control


def make_entry(options=None, data=None):
    return ConfigEntry(
        domain=DOMAIN,
        entry_id="synthetic-entry",
        data=data or {"connection_type":"local", "host":"192.0.2.10", "fingerprint":"synthetic", "password":"PRIVATE-PASSWORD"},
        options=options or {},
        source="user",
        title="WolfLink local",
        unique_id="PRIVATE-USER",
        version=1,
        minor_version=1,
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
        state=ConfigEntryState.SETUP_IN_PROGRESS,
    )


class HomeAssistantTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_polling_option_pending_restore_and_cloud_isolation(self):
        from datetime import timedelta
        from types import SimpleNamespace
        from time import monotonic
        from custom_components.wolflink_local.const import polling_seconds

        entry = SimpleNamespace(
            data={"connection_type": "local"}, options={"poll_interval": 120}
        )
        self.coordinator.entry = entry
        self.coordinator.apply_polling_options()
        self.assertEqual(self.coordinator.update_interval, timedelta(seconds=120))
        self.coordinator._pending_confirmations[1] = (1, monotonic() + 600)
        self.coordinator.apply_polling_options()
        self.assertEqual(self.coordinator.update_interval, timedelta(seconds=15))
        self.coordinator._reconcile_confirmations(Snapshot({(1000, 1): 1}))
        self.assertEqual(self.coordinator.update_interval, timedelta(seconds=120))
        for invalid in (0, 14, 901, "30", True, None):
            entry.options["poll_interval"] = invalid
            self.assertEqual(polling_seconds(entry), 60)
        entry.options["poll_interval"] = 30
        entry.data = {}
        self.assertEqual(polling_seconds(entry), 60)

    async def test_late_schedule_confirmation_uses_time_windows(self):
        target = "06:00-08:00;00:00-00:00;00:00-00:00;00:00-00:00;00:00-00:00"
        from time import monotonic

        self.coordinator._pending_confirmations[32000000000] = (
            target,
            monotonic() + 600,
        )
        self.coordinator._reconcile_confirmations(
            Snapshot({(1000, 32000000000): target})
        )
        self.assertEqual(
            self.coordinator.control_write_status[32000000000], "confirmed"
        )

    async def test_party_button_failure_status_is_visible_on_controls(self):
        from custom_components.wolflink_local.button import TimedModeButton

        button = TimedModeButton(self.coordinator, "party", True)
        self.api.set_timed_mode = AsyncMock(side_effect=WolfError("period_unconfirmed"))
        self.coordinator.async_request_refresh = AsyncMock()
        self.coordinator.api.schedule_acknowledgements = {}
        with self.assertRaises(HomeAssistantError):
            await button.async_press()
        self.assertEqual(button.extra_state_attributes["write_status"], "failed")
        self.coordinator.async_request_refresh.assert_awaited_once()

    async def test_readback_status_shared_by_number_switch_and_program_select(self):
        from custom_components.wolflink_local.switch import WolfHotWaterSwitch

        for entity, value in (
            (WolfNumber(self.coordinator, CONTROLS[34003500000]), "21"),
            (WolfHotWaterSwitch(self.coordinator), "1"),
            (WolfSelect(self.coordinator, CONTROLS[34001600000]), "2"),
        ):
            self.api.write = AsyncMock(
                return_value=WriteOutcome(
                    self.coordinator.definition.metadata, observed=value
                )
            )
            await self.coordinator.async_write_control(
                entity.parameter_id, float(value)
            )
            self.assertEqual(entity.extra_state_attributes["write_status"], "confirmed")

    async def test_colour_status_waits_for_api_and_readback(self):
        requested, transferred, finish = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )

        async def write(*args, progress):
            requested.set()
            await transferred.wait()
            progress("awaiting_confirmation")
            await finish.wait()
            return WriteOutcome(self.coordinator.definition.metadata, observed="2")

        self.api.write = AsyncMock(side_effect=write)
        entity = WolfSelect(self.coordinator, CONTROLS[34002900000])
        task = asyncio.create_task(self.coordinator.async_write_control(34002900000, 2))
        await requested.wait()
        self.assertEqual(entity.extra_state_attributes["write_status"], "sending")
        transferred.set()
        await asyncio.sleep(0)
        self.assertEqual(
            entity.extra_state_attributes["write_status"], "awaiting_confirmation"
        )
        self.assertEqual(entity.confirmed_option, "automatic")
        finish.set()
        await task
        self.assertEqual(entity.extra_state_attributes["write_status"], "confirmed")
        self.assertEqual(entity.confirmed_option, "permanent")

    async def test_mismatch_waits_and_later_poll_confirms(self):
        self.api.write = AsyncMock(
            return_value=WriteOutcome(
                self.coordinator.definition.metadata,
                observed="1",
                error="readback_mismatch",
            )
        )
        await self.coordinator.async_write_control(34002900000, 2)
        self.assertEqual(
            self.coordinator.control_write_status[34002900000], "awaiting_confirmation"
        )
        self.coordinator._reconcile_confirmations(Snapshot({(1000, 34002900000): "1"}))
        self.assertEqual(
            self.coordinator.control_write_status[34002900000], "awaiting_confirmation"
        )
        self.coordinator._reconcile_confirmations(
            Snapshot({(1000, 34002900000): "2.0"})
        )
        self.assertEqual(
            self.coordinator.control_write_status[34002900000], "confirmed"
        )
        self.api.write.assert_awaited_once()

    async def test_pending_confirmation_expires_without_resending(self):
        self.coordinator._pending_confirmations[34002900000] = (2, 0)
        self.coordinator._reconcile_confirmations(Snapshot({(1000, 34002900000): "1"}))
        self.assertEqual(self.coordinator.control_write_status[34002900000], "failed")
        self.assertFalse(self.coordinator._pending_confirmations)
        self.api.write.assert_not_called()

    async def test_mode_forms_are_local_and_buttons_are_explicit(self):
        from custom_components.wolflink_local.number import PartyDuration
        from custom_components.wolflink_local.datetime import HolidayDateTime
        from custom_components.wolflink_local.button import TimedModeButton
        from custom_components.wolflink_local.mode_drafts import draft

        duration = PartyDuration(self.coordinator, "party_minutes")
        await duration.async_set_native_value(90)
        self.assertEqual(duration.native_value, 90)
        with self.assertRaises(HomeAssistantError):
            await duration.async_set_native_value(10)
        field = HolidayDateTime(self.coordinator, "holiday_end")
        from datetime import timedelta

        value = field.native_value + timedelta(days=2)
        await field.async_set_value(value)
        self.assertEqual(draft(self.coordinator)["holiday_end"], value)
        self.assertEqual(self.api.mock_calls, [])
        self.api.set_timed_mode = AsyncMock()
        self.coordinator.async_request_refresh = AsyncMock()
        self.coordinator.api.schedule_acknowledgements = {}
        button = TimedModeButton(self.coordinator, "party", True)
        await button.async_press()
        args = self.api.set_timed_mode.call_args.args
        self.assertEqual(args[1], "party")
        self.assertEqual((args[3].timestamp() - args[2].timestamp()) / 60, 90)
        self.coordinator.async_request_refresh.assert_awaited_once()

    async def test_hot_water_switch_uses_real_state_and_never_starts_on_setup(self):
        from custom_components.wolflink_local.switch import (
            async_setup_entry as setup_switch,
        )

        entities = []
        await setup_switch(self.hass, self.entry, lambda items: entities.extend(items))
        self.assertEqual(len(entities), 1)
        entity = entities[0]
        self.coordinator.async_set_updated_data(Snapshot({(1000, 22004200000): "0"}))
        self.assertFalse(entity.is_on)
        self.api.write.assert_not_called()
        self.coordinator.async_write_control = AsyncMock()
        await entity.async_turn_on()
        self.coordinator.async_write_control.assert_awaited_once_with(22004200000, 1)
        self.assertFalse(entity.is_on)
        self.coordinator.async_set_updated_data(Snapshot({(1000, 22004200000): "1"}))
        self.assertTrue(entity.is_on)
        await entity.async_turn_off()
        self.coordinator.async_write_control.assert_awaited_with(22004200000, 0)
        self.coordinator.async_set_updated_data(Snapshot({(1000, 22004200000): "0"}))
        self.assertFalse(entity.is_on)
        self.coordinator.async_set_updated_data(Snapshot({(1000, 22004200000): "2"}))
        self.assertFalse(entity.available)

    async def test_modes_show_pending_choice_then_confirm_actual_readback(self):
        for pid in (34002900000, 35001200000):
            with patch.object(
                type(self.coordinator),
                "read_only",
                new_callable=PropertyMock,
                return_value=False,
            ):
                self.coordinator.async_set_updated_data(Snapshot({(1000, pid): "1"}))
                entity = WolfSelect(self.coordinator, CONTROLS[pid])
                entity.hass = self.hass
                entity.async_write_ha_state = Mock()
                started, finish = asyncio.Event(), asyncio.Event()

                async def write(*args):
                    started.set()
                    await finish.wait()
                    self.coordinator.async_set_updated_data(
                        Snapshot({(1000, pid): "0"})
                    )

                self.coordinator.async_write_control = AsyncMock(side_effect=write)
                task = asyncio.create_task(entity.async_select_option("standby"))
                await started.wait()
                self.assertEqual(entity.current_option, "standby")
                self.assertEqual(entity.confirmed_option, "automatic")
                self.assertTrue(entity.extra_state_attributes["write_pending"])
                finish.set()
                await task
                self.assertEqual(entity.current_option, "standby")
                self.assertFalse(entity.extra_state_attributes["write_pending"])
                self.assertEqual(entity.async_write_ha_state.call_count, 2)

    async def test_pending_mode_reverts_on_error(self):
        with patch.object(
            type(self.coordinator),
            "read_only",
            new_callable=PropertyMock,
            return_value=False,
        ):
            entity = WolfSelect(self.coordinator, CONTROLS[34002900000])
            self.coordinator.async_write_control = AsyncMock(
                side_effect=HomeAssistantError("test failure")
            )
            with self.assertRaises(HomeAssistantError):
                await entity.async_select_option("standby")
            self.assertEqual(entity.current_option, "automatic")
            self.assertFalse(entity.extra_state_attributes["write_pending"])

    async def test_schedule_preview_service_validates_without_api_access(self):
        from custom_components.wolflink_local.services import register_services

        register_services(self.hass)
        data = {
            "area": "heating",
            "program": 3.0,
            "weekday": "monday",
            "windows": [{"start": "06:00", "end": "22:00"}],
        }
        result = await self.hass.services.async_call(
            DOMAIN,
            "preview_time_program_day",
            data,
            blocking=True,
            return_response=True,
        )
        self.assertFalse(result["transmitted"])
        self.assertFalse(result["write_supported"])
        data["windows"] = [{"start": "22:00", "end": "06:00"}]
        with self.assertRaises(HomeAssistantError):
            await self.hass.services.async_call(
                DOMAIN,
                "preview_time_program_day",
                data,
                blocking=True,
                return_response=True,
            )
        self.assertEqual(self.api.mock_calls, [])

    async def test_schedule_read_service_returns_week_and_marks_missing_days(self):
        from custom_components.wolflink_local.services import register_services
        from custom_components.wolflink_local.time_program import (
            WEEKDAYS,
            parameter_for,
        )

        values = {
            (
                1000,
                parameter_for("heating", 3, day),
            ): "06:00-22:00;00:00-00:00;00:00-00:00;00:00-00:00;00:00-00:00"
            for day in WEEKDAYS
        }
        values[(1000, 34001600000)] = "3"
        self.coordinator.async_set_updated_data(Snapshot(values))
        self.coordinator.async_request_refresh = AsyncMock()
        self.coordinator.api.schedule_acknowledgements = {}
        self.hass.config_entries = Mock(
            async_loaded_entries=Mock(return_value=[self.entry])
        )
        device = Mock(identifiers={(DOMAIN, self.coordinator.device_key)})
        registry = Mock(async_get=Mock(return_value=device))
        register_services(self.hass)
        with patch(
            "custom_components.wolflink_local.services.dr.async_get",
            return_value=registry,
        ):

            async def read():
                return await self.hass.services.async_call(
                    DOMAIN,
                    "get_time_program",
                    {"device_id": "synthetic", "area": "heating", "program": 3},
                    blocking=True,
                    return_response=True,
                )

            result = await read()
            self.assertTrue(result["complete"])
            self.assertEqual(result["active_program"], 3)
            self.assertEqual(len(result["days"]), 7)
            del values[(1000, parameter_for("heating", 3, "monday"))]
            result = await read()
            self.assertFalse(result["complete"])
            self.assertEqual(
                result["days"]["monday"]["status"], "unavailable_or_unsupported_format"
            )
            self.coordinator.last_update_success = False
            with self.assertRaises(HomeAssistantError):
                await read()
        self.assertEqual(self.api.mock_calls, [])

    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.folder.name)
        self.entry = make_entry()
        self.api = Mock()
        self.device = Device(111, 222, "PRIVATE-DEVICE")
        self.coordinator = WolfLinkCoordinator(
            self.hass, self.entry, self.api, self.device
        )
        metadata = {}
        for pid in CONTROLS:
            raw = raw_control(pid)
            metadata[pid] = ParameterMeta(pid, pid, 1000, raw["Name"], raw)
        self.coordinator.definition = Definition([], metadata)
        self.coordinator.async_set_updated_data(
            Snapshot(
                {
                    (1000, 34002900000): "1",
                    (1000, 35000900000): "40",
                    (1000, 34002600000): "-0.5",
                }
            )
        )
        self.entry.runtime_data = Runtime(self.api, [self.coordinator], Mock())

    async def asyncTearDown(self):
        await self.coordinator.async_shutdown()
        await self.hass.async_stop()
        self.folder.cleanup()

    async def test_select_uses_reported_state_and_all_four_options(self):
        entity = WolfSelect(self.coordinator, CONTROLS[34002900000])
        self.assertEqual(
            entity.options, ["standby", "automatic", "permanent", "economy"]
        )
        self.assertEqual(entity.current_option, "automatic")
        self.coordinator.async_set_updated_data(Snapshot({(1000, 34002900000): "3"}))
        self.assertEqual(entity.current_option, "economy")
        self.coordinator.async_set_updated_data(Snapshot({(1000, 34002900000): "99"}))
        self.assertIsNone(entity.current_option)
        self.assertFalse(entity.available)

    async def test_both_program_selects_read_current_value_instead_of_initial_default(
        self,
    ):
        for pid in (34001600000, 35000400000):
            entity = WolfSelect(self.coordinator, CONTROLS[pid])
            self.coordinator.async_set_updated_data(Snapshot({(1000, pid): "3"}))
            self.assertEqual(entity.current_option, "3")
            self.coordinator.async_set_updated_data(Snapshot({(1000, pid): "1"}))
            self.assertEqual(entity.current_option, "1")

    async def test_select_passes_only_mapped_code_and_never_sets_optimistic_state(self):
        entity = WolfSelect(self.coordinator, CONTROLS[34002900000])
        self.coordinator.async_write_control = AsyncMock()
        await entity.async_select_option("permanent")
        self.coordinator.async_write_control.assert_awaited_once_with(34002900000, 2)
        self.assertEqual(entity.current_option, "automatic")
        with self.assertRaises(HomeAssistantError):
            await entity.async_select_option("invalid")

    async def test_number_entities_use_correct_grid_and_observed_value(self):
        target = WolfNumber(self.coordinator, CONTROLS[35000900000])
        offset = WolfNumber(self.coordinator, CONTROLS[34002600000])
        self.assertEqual(
            (target.native_min_value, target.native_max_value, target.native_step),
            (25, 65, 1),
        )
        self.assertEqual(
            (offset.native_min_value, offset.native_max_value, offset.native_step),
            (-4, 4, 0.5),
        )
        self.assertEqual(offset.native_value, -0.5)
        self.coordinator.async_write_control = AsyncMock()
        await target.async_set_native_value(41)
        self.coordinator.async_write_control.assert_awaited_once_with(35000900000, 41)
        self.assertEqual(target.native_value, 40)

    async def test_default_read_only_and_actual_readback_on_mismatch(self):
        self.assertTrue(self.coordinator.read_only)
        outcome = WriteOutcome(
            self.coordinator.definition.metadata,
            observed="0",
            error="readback_mismatch",
        )
        self.api.write = AsyncMock(return_value=outcome)
        await self.coordinator.async_write_control(34002900000, 2)
        self.assertEqual(self.coordinator.data.values[(1000, 34002900000)], "0")
        args = self.api.write.call_args.args
        self.assertTrue(args[-1]())

    async def test_failed_readback_clears_target_instead_of_reporting_success(self):
        self.api.write = AsyncMock(
            return_value=WriteOutcome(
                self.coordinator.definition.metadata, error="readback_failed"
            )
        )
        await self.coordinator.async_write_control(34002900000, 2)
        self.assertNotIn((1000, 34002900000), self.coordinator.data.values)

    async def test_network_failure_marks_all_entities_unavailable(self):
        self.api.write = AsyncMock(side_effect=WolfError("offline"))
        entity = WolfSelect(self.coordinator, CONTROLS[34002900000])
        with self.assertRaises(HomeAssistantError):
            await self.coordinator.async_write_control(34002900000, 2)
        self.assertFalse(entity.available)

    async def test_original_sensor_classes_units_state_and_device_identity(self):
        param = Temperature(99001, "Synthetic temperature", "User", 99001, 1000, True)
        desc = next(d for d in SENSOR_DESCRIPTIONS if d.supported_fn(param))
        sensor = WolfLinkSensor(self.coordinator, param, desc)
        self.coordinator.async_set_updated_data(Snapshot({(1000, 99001): "21.5"}))
        self.assertEqual(sensor.native_value, 21.5)
        self.assertEqual(sensor.native_unit_of_measurement, "°C")
        self.assertEqual(
            sensor.device_info["identifiers"], {(DOMAIN, self.coordinator.device_key)}
        )
        self.coordinator.async_set_updated_data(Snapshot())
        self.assertFalse(sensor.available)
        self.assertIsNone(sensor.native_value)
        enum = ListItemParameter(
            99002, "Synthetic enum", "User", [ListItem(1, "Ein")], 99002, 1000, True
        )
        enum_desc = next(d for d in SENSOR_DESCRIPTIONS if d.supported_fn(enum))
        enum_sensor = WolfLinkSensor(self.coordinator, enum, enum_desc)
        self.coordinator.async_set_updated_data(Snapshot({(1000, 99002): "1"}))
        self.assertEqual(enum_sensor.native_value, "ein")

    async def test_schedules_are_read_only_and_disabled_by_default(self):
        sensor = DailyScheduleSensor(self.coordinator, 32004100000)
        self.assertFalse(sensor.entity_registry_enabled_default)
        self.assertEqual(
            (sensor.area, sensor.program, sensor.day), ("hot_water", 3, "Sunday")
        )
        self.assertTrue(sensor.extra_state_attributes["read_only"])
        self.assertFalse(hasattr(sensor, "async_set_native_value"))

    async def test_all_upstream_numeric_sensor_classes_and_simple_sensor(self):
        from custom_components.wolflink_local import models

        cases = [
            (models.Temperature, "°C"),
            (models.Pressure, "bar"),
            (models.EnergyParameter, "kWh"),
            (models.PowerParameter, "kW"),
            (models.PercentageParameter, "%"),
            (models.HoursParameter, "h"),
            (models.FlowParameter, "L/min"),
            (models.FrequencyParameter, "Hz"),
            (models.RPMParameter, "rpm"),
            (models.SimpleParameter, None),
        ]
        for model, unit in cases:
            with self.subTest(model=model.__name__):
                param = model(99003, "Synthetic value", "User", 99003, 1000, True)
                descriptions = [
                    desc for desc in SENSOR_DESCRIPTIONS if desc.supported_fn(param)
                ]
                self.assertEqual(len(descriptions), 1)
                entity = WolfLinkSensor(self.coordinator, param, descriptions[0])
                self.coordinator.async_set_updated_data(Snapshot({(1000, 99003): "5"}))
                self.assertEqual(entity.native_unit_of_measurement, unit)
                self.assertEqual(entity.native_value, "5" if unit is None else 5)

    async def test_diagnostics_omit_all_private_data_and_actual_values(self):
        data = await async_get_config_entry_diagnostics(self.hass, self.entry)
        serialized = json.dumps(data)
        for text in ["PRIVATE", '"values"', "-0.5", "synthetic-entry"]:
            self.assertNotIn(text, serialized)
        self.assertTrue(data["read_only"])

    async def test_user_flow_opens_local_configuration_only(self):
        flow = WolfLinkConfigFlow()
        flow.hass = self.hass
        result = await flow.async_step_user()
        self.assertEqual(result["step_id"], "local")
        self.assertFalse(hasattr(flow, "async_step_cloud"))

    async def test_options_flow_requires_explicit_false_to_allow_writes(self):
        flow = WolfLinkOptionsFlow()
        flow.hass = self.hass
        flow.handler = DOMAIN
        with patch.object(
            WolfLinkOptionsFlow,
            "config_entry",
            new_callable=PropertyMock,
            return_value=self.entry,
        ):
            form = await flow.async_step_init()
            self.assertTrue(form["data_schema"]({})["read_only"])
            result = await flow.async_step_init({"read_only": False})
            self.assertEqual(result["data"], {"read_only": False, "poll_interval": 60})

    async def test_local_options_interval_bounds_and_preserves_other_options(self):
        from types import SimpleNamespace
        import probatio

        flow = WolfLinkOptionsFlow()
        flow.hass = self.hass
        flow.handler = DOMAIN
        entry = SimpleNamespace(
            data={"connection_type": "local"},
            options={"read_only": False, "preserved": "value"},
        )
        with patch.object(
            WolfLinkOptionsFlow,
            "config_entry",
            new_callable=PropertyMock,
            return_value=entry,
        ):
            schema = (await flow.async_step_init())["data_schema"]
            self.assertEqual(schema({})["poll_interval"], 60)
            for value in (15, 30, 60, 900):
                self.assertEqual(
                    schema({"poll_interval": value})["poll_interval"], value
                )
            for value in (14, 901, "30", 30.5):
                with self.assertRaises(probatio.Invalid):
                    schema({"poll_interval": value})
            result = await flow.async_step_init(
                {"read_only": False, "poll_interval": 30}
            )
            self.assertEqual(
                result["data"],
                {"read_only": False, "poll_interval": 30, "preserved": "value"},
            )

    async def test_local_reauthentication_preserves_write_permission(self):
        for read_only in (False, True):
            entry = make_entry({"read_only": read_only}, {"connection_type": "local"})
            flow = WolfLinkConfigFlow()
            flow.hass = self.hass
            flow.context = {"source": "reauth"}
            flow._get_reauth_entry = Mock(return_value=entry)
            flow._validate = AsyncMock()
            flow.async_update_reload_and_abort = Mock(return_value={"type":"abort"})
            self.hass.config_entries = Mock()
            await flow.async_step_reauth_confirm({"password":"synthetic-new-password"})
            self.hass.config_entries.async_update_entry.assert_not_called()
            self.assertEqual(entry.options["read_only"], read_only)

    async def test_config_validation_closes_own_client_on_auth_error(self):
        flow = WolfLinkConfigFlow()
        flow.hass = self.hass
        api = Mock(aclose=AsyncMock(), systems=AsyncMock(side_effect=WolfError("invalid_auth")))
        with patch("custom_components.wolflink_local.config_flow.LocalWolfApi.create",new=AsyncMock(return_value=api)):
            with self.assertRaises(WolfError):
                await flow._validate({"host":"192.0.2.10", "password":"synthetic"})
        api.aclose.assert_awaited_once()

    async def test_platform_setup_creates_four_selects_and_three_user_numbers(self):
        from custom_components.wolflink_local.select import (
            async_setup_entry as setup_select,
        )
        from custom_components.wolflink_local.number import (
            async_setup_entry as setup_number,
        )

        entities = []
        await setup_select(
            self.hass, self.entry, lambda values: entities.extend(values)
        )
        await setup_number(
            self.hass, self.entry, lambda values: entities.extend(values)
        )
        self.assertEqual(len(entities), 7)
        self.assertEqual(len({entity.unique_id for entity in entities}), 7)

    async def test_day_temperature_entity_uses_celsius_and_actual_readback(self):
        entity = WolfNumber(self.coordinator, CONTROLS[34003500000])
        self.coordinator.async_set_updated_data(Snapshot({(1000, 34003500000): "20.5"}))
        self.assertEqual(entity.native_value, 20.5)
        self.assertEqual(entity.native_min_value, 5)
        self.assertEqual(entity.native_max_value, 30)
        self.assertEqual(entity.native_step, 0.5)
        self.assertEqual(entity.native_unit_of_measurement, "°C")
        self.coordinator.async_write_control = AsyncMock()
        await entity.async_set_native_value(21)
        self.coordinator.async_write_control.assert_awaited_once_with(34003500000, 21)
        self.assertEqual(entity.native_value, 20.5)

    async def test_entry_setup_and_unload_use_real_coordinator_without_writes(self):
        http = Mock(aclose=AsyncMock())
        api = Mock(aclose=http.aclose,
            systems=AsyncMock(return_value=[self.device]),
            discover=AsyncMock(return_value=self.coordinator.definition),
            read=AsyncMock(return_value=self.coordinator.data),
            write=AsyncMock(),
        )
        self.hass.config_entries = Mock(
            async_forward_entry_setups=AsyncMock(),
            async_unload_platforms=AsyncMock(return_value=True),
            async_loaded_entries=Mock(return_value=[]),
        )
        with (
            patch(
                "custom_components.wolflink_local.LocalWolfApi.create",
                new=AsyncMock(return_value=api),
            ),
            patch("custom_components.wolflink_local.async_register", new=AsyncMock()),
            patch("custom_components.wolflink_local.async_unregister"),
        ):
            self.assertTrue(await async_setup_entry(self.hass, self.entry))
            api.write.assert_not_called()
            self.assertTrue(self.entry.runtime_data.coordinators[0].read_only)
            self.assertTrue(await async_unload_entry(self.hass, self.entry))
            http.aclose.assert_awaited_once()
            for coordinator in self.entry.runtime_data.coordinators:
                await coordinator.async_shutdown()
