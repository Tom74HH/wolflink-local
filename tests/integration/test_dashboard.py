"""Portable UI uses device-scoped registry identities, never example entity IDs."""

import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import TestCase, IsolatedAsyncioTestCase
from unittest.mock import Mock, patch, AsyncMock
import sys
from types import ModuleType

from custom_components.wolflink_local.dashboard import bind_template, build_config


class DashboardTests(TestCase):
    def test_missing_controls_are_removed(self):
        self.assertEqual(
            bind_template(
                [{"entity": "@1:number"}, {"entity": "@2:sensor"}],
                {"2:sensor": "sensor.renamed"},
                "device",
            ),
            [{"entity": "sensor.renamed"}],
        )
        self.assertEqual(bind_template("@device", {}, "own-device"), "own-device")

    def test_real_bundle_renames_multiple_devices_and_disabled_entities(self):
        bundle = json.loads(
            Path("custom_components/wolflink_local/frontend/dashboard.json").read_text(
                encoding="utf8"
            )
        )
        roles = set(bundle["sensors"].values())

        def collect(v):
            if isinstance(v, dict):
                for x in v.values():
                    collect(x)
            elif isinstance(v, list):
                for x in v:
                    collect(x)
            elif isinstance(v, str) and v.startswith("@") and v != "@device":
                roles.add(v[1:])

        collect(bundle["template"])
        entities = {}
        for device in ("one", "two"):
            for i, role in enumerate(sorted(roles)):
                entity_id = f"{('sensor' if role.endswith('sensor') else 'select')}.{device}_renamed_{i}"
                entities[entity_id] = NS(
                    platform="wolflink_local",
                    config_entry_id="entry",
                    device_id=device,
                    unique_id=f"entry:gateway:{device}:{role}",
                    entity_id=entity_id,
                    disabled=False,
                )
        disabled = NS(
            platform="wolflink_local",
            config_entry_id="entry",
            device_id="one",
            unique_id="entry:gateway:one:999:sensor",
            entity_id="sensor.disabled",
            disabled=True,
        )
        entities["disabled"] = disabled
        entry = NS(
            entry_id="entry",
            data={},
            runtime_data=NS(
                coordinators=[
                    NS(
                        device_key=f"entry:gateway:{device}",
                        device=NS(name=f"Own {device}"),
                    )
                    for device in ("one", "two")
                ]
            ),
        )
        devices = Mock()
        devices.async_get_device.side_effect = lambda identifiers: NS(
            id=next(iter(identifiers))[1].split(":")[-1]
        )
        with (
            patch(
                "custom_components.wolflink_local.dashboard.er.async_get",
                return_value=NS(entities=entities),
            ),
            patch(
                "custom_components.wolflink_local.dashboard.dr.async_get",
                return_value=devices,
            ),
        ):
            config = build_config(Mock(), {"entry": entry}, bundle)
        self.assertEqual(len(config["views"]), 2)
        for view, device, other in zip(config["views"], ("one", "two"), ("two", "one")):
            encoded = json.dumps(view)
            self.assertIn(f"{device}_renamed_", encoded)
            self.assertNotIn(f"{other}_renamed_", encoded)
            self.assertNotIn('"@', encoded)
            self.assertNotIn("DEINE_WOLF", encoded)
            self.assertNotIn("sensor.disabled", encoded)


class RegistrationTests(IsolatedAsyncioTestCase):
    async def test_registration_collision_multiple_entries_reload_and_cleanup(self):
        from custom_components.wolflink_local import dashboard as module

        frontend = ModuleType("homeassistant.components.frontend")
        frontend.async_panel_exists = Mock(return_value=False)
        for name in (
            "add_extra_js_url",
            "remove_extra_js_url",
            "async_register_built_in_panel",
            "async_remove_panel",
        ):
            setattr(frontend, name, Mock())
        http = ModuleType("homeassistant.components.http")
        http.StaticPathConfig = lambda *args: args
        lovelace = ModuleType("homeassistant.components.lovelace")
        const = ModuleType("homeassistant.components.lovelace.const")
        const.LOVELACE_DATA = "lovelace"
        dashboard = ModuleType("homeassistant.components.lovelace.dashboard")

        class Base:
            def __init__(self, *args):
                pass

            def _config_updated(self):
                pass

        dashboard.LovelaceConfig = Base
        modules = {m.__name__: m for m in (frontend, http, lovelace, const, dashboard)}
        hass = NS(
            data={"lovelace": NS(dashboards={"wolflink-local": "user-owned"})},
            http=NS(async_register_static_paths=AsyncMock()),
            async_add_executor_job=AsyncMock(side_effect=lambda fn: fn()),
        )
        first, second = NS(entry_id="one"), NS(entry_id="two")
        with patch.dict(sys.modules, modules):
            await module.async_register(hass, first)
            state = hass.data[module.DATA]
            self.assertEqual(state["path"], "wolflink-local-local")
            await module.async_register(hass, second)
            hass.http.async_register_static_paths.assert_awaited_once()
            module.async_unregister(hass, first)
            frontend.async_remove_panel.assert_not_called()
            module.async_unregister(hass, second)
            self.assertEqual(
                hass.data["lovelace"].dashboards, {"wolflink-local": "user-owned"}
            )
            frontend.remove_extra_js_url.assert_called_once_with(hass, module.MODULE)
            await module.async_register(hass, first)
            hass.http.async_register_static_paths.assert_awaited_once()
            module.async_unregister(hass, first)

