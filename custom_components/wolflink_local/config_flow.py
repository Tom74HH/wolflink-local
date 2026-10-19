"""UI configuration, reauthentication, and explicit read-only option."""

import probatio

from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import callback

from .const import (
    CONF_READ_ONLY,
    CONF_POLL_INTERVAL,
    DOMAIN,
    MIN_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
    polling_seconds,
)
from .controls import WolfError
from .local_api import LocalWolfApi

class WolfLinkConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, data):
        api = await LocalWolfApi.create(self.hass, data["host"], data[CONF_PASSWORD], data.get("fingerprint"), data.get("module_identity"))
        try:
            await api.systems()
        finally:
            await api.aclose()

    async def async_step_user(self, user_input=None):
        return await self.async_step_local(user_input)

    async def async_step_local(self, user_input=None):
        errors = {}
        if user_input is not None:
            api = None
            try:
                api = await LocalWolfApi.create(
                    self.hass, user_input["host"].strip(), user_input[CONF_PASSWORD]
                )
                systems = await api.systems()
                await self.async_set_unique_id(f"local:{systems[0].id}")
                self._abort_if_unique_id_configured()
                self._local_data = {
                    "connection_type": "local",
                    "host": api.host,
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    "fingerprint": api.fingerprint,
                    "module_identity": systems[0].id,
                }
            except WolfError as exc:
                errors["base"] = (
                    exc.code
                    if exc.code in ("invalid_auth", "local_unsupported_system")
                    else "cannot_connect"
                )
            else:
                return await self.async_step_local_confirm()
            finally:
                if api is not None:
                    await api.aclose()
        return self.async_show_form(
            step_id="local",
            data_schema=probatio.Schema(
                {probatio.Required("host"): str, probatio.Required(CONF_PASSWORD): str}
            ),
            errors=errors,
        )

    async def async_step_local_confirm(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="WolfLink local",
                data=self._local_data,
                options={CONF_READ_ONLY: True},
            )
        return self.async_show_form(
            step_id="local_confirm",
            data_schema=probatio.Schema({}),
            description_placeholders={"fingerprint": self._local_data["fingerprint"]},
        )

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = dict(entry.data, **user_input)
            try:
                await self._validate(data)
            except WolfError as exc:
                errors["base"] = (
                    "invalid_auth" if exc.code == "invalid_auth" else "cannot_connect"
                )
            else:
                return self.async_update_reload_and_abort(entry, data_updates=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=probatio.Schema({probatio.Required(CONF_PASSWORD): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return WolfLinkOptionsFlow()


class WolfLinkOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        local = self.config_entry.data.get("connection_type") == "local"
        if user_input is not None:
            data = {
                **self.config_entry.options,
                CONF_READ_ONLY: user_input[CONF_READ_ONLY] is not False,
            }
            if local:
                data[CONF_POLL_INTERVAL] = user_input.get(CONF_POLL_INTERVAL, polling_seconds(self.config_entry))
            return self.async_create_entry(title="", data=data)
        fields = {
            probatio.Required(
                CONF_READ_ONLY,
                default=self.config_entry.options.get(CONF_READ_ONLY, True),
            ): bool
        }
        if local:
            fields[
                probatio.Required(
                    CONF_POLL_INTERVAL, default=polling_seconds(self.config_entry)
                )
            ] = probatio.All(
                int, probatio.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL)
            )
        return self.async_show_form(
            step_id="init",
            data_schema=probatio.Schema(fields),
        )
