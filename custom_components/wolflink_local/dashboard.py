"""Bundled, generated Lovelace dashboard; no user dashboard files are modified."""

import json
import asyncio
from pathlib import Path

from homeassistant.helpers import entity_registry as er, device_registry as dr

from .const import DOMAIN, VERSION

DATA = DOMAIN + "_dashboard"
ASSETS = Path(__file__).parent / "frontend"
URL = "/wolflink_local_static"
MODULE = f"{URL}/wolflink-mode-popup.js?v={VERSION}"


def bind_template(value, entities, device_id):
    """Resolve role tokens within one device, omitting unsupported entity cards."""
    if isinstance(value, str):
        if value == "@device":
            return device_id
        if value.startswith("@"):
            return entities.get(value[1:])
        return value
    if isinstance(value, list):
        return [
            bound
            for item in value
            if (bound := bind_template(item, entities, device_id)) is not None
        ]
    if isinstance(value, dict):
        bound = {
            key: bind_template(item, entities, device_id) for key, item in value.items()
        }
        if "entity" in bound and bound["entity"] is None:
            return None
        return bound
    return value


def build_config(hass, entries, bundle):
    """Discover registry identities anew, including renamed entities and multiple systems."""
    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    views = []
    for entry in entries.values():
        for coordinator in entry.runtime_data.coordinators:
            prefix = coordinator.device_key + ":"
            device = devices.async_get_device(
                identifiers={(DOMAIN, coordinator.device_key)}
            )
            if device is None:
                continue
            entities = {
                entity.unique_id[len(prefix) :]: entity.entity_id
                for entity in registry.entities.values()
                if entity.platform == DOMAIN
                and entity.config_entry_id == entry.entry_id
                and entity.device_id == device.id
                and entity.unique_id.startswith(prefix)
                and not entity.disabled
            }
            config = bind_template(bundle["template"], entities, device.id)
            local_api = getattr(coordinator, "api", None)
            schedules = getattr(local_api, "supports_schedule", True)
            periods = getattr(local_api, "supports_timed_modes", True)
            if schedules is False or periods is False:

                def local_cards(value):
                    if isinstance(value, list):
                        return [local_cards(item) for item in value]
                    if not isinstance(value, dict):
                        return value
                    result = {key: local_cards(item) for key, item in value.items()}
                    role = result.get("wolf_role", "")
                    unsupported = (not schedules and "zeitprogramm" in role) or (
                        not periods and ("partymodus" in role or "urlaubsmodus" in role)
                    )
                    if (
                        result.get("type") == "custom:wolflink-mode-popup"
                        and unsupported
                    ):
                        result.pop("cards", None)
                        result["type"] = "custom:wolflink-write-status"
                    return result

                config = local_cards(config)
            view = config["views"][0]
            view["title"] = "Wolflink local"
            view.pop("icon", None)
            view["path"] = f"system-{len(views) + 1}"
            for section in view["sections"]:
                for card in section["cards"]:
                    if card["type"] == "custom:wolflink-plant-dashboard":
                        if entry.data.get("connection_type") == "local":
                            card["credit"] = "Tom74HH"
                        card["sensors"] = {
                            key: entities[role]
                            for key, role in bundle["sensors"].items()
                            if role in entities
                        }
            views.append(view)
    return {"title": "WolfLink local", "views": views}


async def async_register(hass, entry):
    """Serialize UI setup when multiple accounts load concurrently."""
    lock = hass.data.setdefault(DATA + "_lock", asyncio.Lock())
    async with lock:
        await _async_register_locked(hass, entry)


async def _async_register_locked(hass, entry):
    """Serve packaged assets and register one generated dashboard for all entries."""
    from homeassistant.components import frontend
    from homeassistant.components.http import StaticPathConfig
    from homeassistant.components.lovelace.const import LOVELACE_DATA
    from homeassistant.components.lovelace.dashboard import LovelaceConfig
    from homeassistant.helpers.json import cached_json_fragment

    state = hass.data.get(DATA)
    if state is not None:
        state["entries"][entry.entry_id] = entry
        state["dashboard"]._config_updated()
        return

    bundle = await hass.async_add_executor_job(
        lambda: json.loads((ASSETS / "dashboard.json").read_text(encoding="utf8"))
    )
    if not hass.data.get(DATA + "_static"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL, str(ASSETS), False)]
        )
        hass.data[DATA + "_static"] = True
    entries = {entry.entry_id: entry}

    class GeneratedDashboard(LovelaceConfig):
        @property
        def mode(self):
            return "yaml"

        async def async_load(self, force):
            return build_config(hass, entries, bundle)

        async def async_json(self, force):
            return cached_json_fragment(await self.async_load(force))

        async def async_get_info(self):
            return {
                "mode": self.mode,
                "views": len((await self.async_load(False))["views"]),
            }

    dashboards = hass.data[LOVELACE_DATA].dashboards
    path = "wolflink-local"
    while path in dashboards or frontend.async_panel_exists(hass, path):
        path += "-local"
    dashboard = GeneratedDashboard(hass, path, {"title": "WolfLink local"})
    frontend.add_extra_js_url(hass, MODULE)
    frontend.async_register_built_in_panel(
        hass,
        "lovelace",
        frontend_url_path=path,
        sidebar_title="WolfLink local",
        sidebar_icon="mdi:radiator",
        config={"mode": "yaml"},
        require_admin=False,
    )
    dashboards[path] = dashboard
    hass.data[DATA] = {"entries": entries, "dashboard": dashboard, "path": path}


def async_unregister(hass, entry):
    """Remove only the dashboard owned by this integration on last unload."""
    state = hass.data.get(DATA)
    if state is None:
        return
    state["entries"].pop(entry.entry_id, None)
    if state["entries"]:
        state["dashboard"]._config_updated()
        return
    from homeassistant.components import frontend
    from homeassistant.components.lovelace.const import LOVELACE_DATA

    hass.data[LOVELACE_DATA].dashboards.pop(state["path"], None)
    frontend.async_remove_panel(hass, state["path"])
    frontend.remove_extra_js_url(hass, MODULE)
    hass.data.pop(DATA)
