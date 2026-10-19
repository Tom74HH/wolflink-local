"""WolfLink local: sensors plus six explicitly allowed controls."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import DOMAIN
from .controls import WolfError
from .coordinator import WolfLinkCoordinator
from .services import register_services, unregister_services_if_unused
from .dashboard import async_register, async_unregister
from .local_api import LocalWolfApi

PLATFORMS = [
    Platform.SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.DATETIME,
    Platform.BUTTON,
]


@dataclass
class Runtime:
    api: LocalWolfApi
    coordinators: list[WolfLinkCoordinator]
    http: object


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get("connection_type") != "local":
        raise ConfigEntryNotReady("WolfLink local supports ISM7 local connections only")
    http = await LocalWolfApi.create(hass, entry.data["host"], entry.data[CONF_PASSWORD], entry.data["fingerprint"], entry.data.get("module_identity"))
    try:
        api = http
        devices = await api.systems()
        if not devices:
            raise WolfError("no_devices")
        coordinators = []
        # All systems must finish setup or HA retries the entry. A transient
        # failure must not silently lose an entire system until the next restart.
        for device in devices:
            coordinator = WolfLinkCoordinator(hass, entry, api, device)
            await coordinator.async_config_entry_first_refresh()
            coordinators.append(coordinator)
    except WolfError as exc:
        await http.aclose()
        if exc.code == "invalid_auth":
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key=exc.code
            ) from None
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key=exc.code
        ) from None
    except Exception:
        await http.aclose()
        raise
    if entry.title == "WOLF Lokal (ISM7)":
        hass.config_entries.async_update_entry(entry, title="WolfLink local")
    entry.runtime_data = Runtime(api, coordinators, http)
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await http.aclose()
        raise
    try:
        await async_register(hass, entry)
    except Exception:
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        await http.aclose()
        raise
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    register_services(hass)
    return True


async def _options_updated(hass, entry):
    # No reload or startup write. Entry options are consulted again immediately
    # before sending any queued command.
    for coordinator in entry.runtime_data.coordinators:
        coordinator.apply_polling_options()
        coordinator.async_update_listeners()


async def async_unload_entry(hass, entry):
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.http.aclose()
    async_unregister(hass, entry)
    unregister_services_if_unused(hass)
    return True
