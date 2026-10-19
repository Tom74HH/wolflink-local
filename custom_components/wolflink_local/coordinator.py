"""Home Assistant coordinator, actual-state writes and options enforcement."""

from datetime import timedelta
import asyncio
import logging
from time import monotonic

from .models import Device

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Definition, Snapshot
from .local_api import LocalWolfApi
from .const import CONF_READ_ONLY, DOMAIN, polling_seconds
from .controls import BUNDLE, WolfError, decimal_value

_LOGGER = logging.getLogger(__name__)


class WolfLinkCoordinator(DataUpdateCoordinator[Snapshot]):
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: LocalWolfApi, device: Device
    ):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=polling_seconds(entry)),
        )
        self.entry = entry
        self.api = api
        self.device = device
        self.definition: Definition | None = None
        self._refetch = False
        self.control_write_status = {}
        self._pending_confirmations = {}
        self.timed_mode_lock = asyncio.Lock()

    @property
    def read_only(self):
        return self.entry.options.get(CONF_READ_ONLY, True) is not False

    def apply_polling_options(self):
        """Use configured normal cadence, temporarily faster for pending readback."""
        seconds = polling_seconds(self.entry)
        self.update_interval = timedelta(
            seconds=min(seconds, 15) if self._pending_confirmations else seconds
        )

    @property
    def device_key(self):
        return f"{self.entry.entry_id}:{self.device.gateway}:{self.device.id}"

    @property
    def parameters(self):
        return self.definition.sensors

    async def _async_setup(self):
        try:
            self.definition = await self.api.discover(self.device)
        except WolfError as exc:
            self._raise_update_error(exc)

    @staticmethod
    def _raise_update_error(exc):
        if exc.code == "invalid_auth":
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from None
        raise UpdateFailed(
            translation_domain=DOMAIN, translation_key=exc.code
        ) from None

    async def _async_update_data(self):
        try:
            if self._refetch:
                self.definition = await self.api.discover(self.device)
                self._refetch = False
            snapshot = await self.api.read(self.device, self.definition)
            from .controls import CONTROLS

            if any(
                pid in self.definition.metadata and (BUNDLE, pid) not in snapshot.values
                for pid in CONTROLS
            ):
                self._refetch = True
            self._reconcile_confirmations(snapshot)
            return snapshot
        except WolfError as exc:
            self._refetch = True
            self._raise_update_error(exc)

    def _reconcile_confirmations(self, snapshot):
        """Recheck accepted writes on every poll, without resending commands."""
        for pid, (target, deadline) in list(self._pending_confirmations.items()):
            observed = snapshot.values.get((BUNDLE, pid))
            try:
                from .controls import DAILY_IDS
                from .time_program import parse_day

                if pid in DAILY_IDS:
                    matches = observed is not None and parse_day(observed) == parse_day(
                        target
                    )
                else:
                    matches = observed is not None and decimal_value(
                        observed
                    ) == decimal_value(target)
            except WolfError:
                matches = False
            if matches:
                self.control_write_status[pid] = "confirmed"
                del self._pending_confirmations[pid]
            elif monotonic() >= deadline:
                self.control_write_status[pid] = "failed"
                del self._pending_confirmations[pid]
        self.apply_polling_options()

    def _set_write_status(self, parameter_id, status):
        self.control_write_status[parameter_id] = status
        self.async_update_listeners()

    async def async_write_control(self, parameter_id, value):
        self._pending_confirmations.pop(parameter_id, None)
        self._set_write_status(parameter_id, "sending")
        try:
            outcome = await self.api.write(
                self.device,
                parameter_id,
                value,
                lambda: self.read_only,
                progress=lambda status: self._set_write_status(parameter_id, status),
            )
        except WolfError as exc:
            self._set_write_status(parameter_id, "failed")
            if exc.code in (
                "offline",
                "cannot_connect",
                "invalid_auth",
                "read_failed",
                "malformed_response",
            ):
                self.async_set_update_error(
                    UpdateFailed(translation_domain=DOMAIN, translation_key=exc.code)
                )
            elif exc.code == "readback_failed" and self.data:
                values = dict(self.data.values) if self.last_update_success else {}
                values.pop((BUNDLE, parameter_id), None)
                self.async_set_updated_data(Snapshot(values))
            self._refetch = True
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key=exc.code
            ) from None
        except asyncio.CancelledError:
            self._set_write_status(parameter_id, "failed")
            raise
        except Exception:
            self._set_write_status(parameter_id, "failed")
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="write_failed"
            ) from None
        self.definition.metadata = outcome.metadata
        # Publish only the freshly observed value. Keep unrelated readings, and
        # clear this point if readback failed. Never publish the requested value.
        values = (
            dict(self.data.values) if self.last_update_success and self.data else {}
        )
        values.pop((BUNDLE, parameter_id), None)
        if outcome.has_observed_value:
            values[(BUNDLE, parameter_id)] = outcome.observed
        pending = outcome.error in ("readback_failed", "readback_mismatch")
        if pending:
            self._pending_confirmations[parameter_id] = (value, monotonic() + 600)
            self.update_interval = timedelta(seconds=15)
        self.control_write_status[parameter_id] = (
            "awaiting_confirmation"
            if pending
            else "failed"
            if outcome.error
            else "confirmed"
        )
        self.async_set_updated_data(Snapshot(values))
        if outcome.error and not pending:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key=outcome.error
            ) from None

    async def async_write_schedule_day(self, area, program, weekday, windows, expected):
        from .time_program import parameter_for

        pid = parameter_for(area, program, weekday)
        async with self.timed_mode_lock:
            self._pending_confirmations.pop(pid, None)
            self._set_write_status(pid, "sending")
            try:
                _, target, outcome = await self.api.write_schedule_day(
                    self.device,
                    area,
                    program,
                    weekday,
                    windows,
                    expected,
                    lambda: self.read_only,
                    progress=lambda status: self._set_write_status(pid, status),
                )
            except (Exception, asyncio.CancelledError) as exc:
                self._set_write_status(pid, "failed")
                if isinstance(exc, asyncio.CancelledError):
                    raise
                code = exc.code if isinstance(exc, WolfError) else "write_failed"
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key=code
                ) from None
            self.definition.metadata = outcome.metadata
            values = (
                dict(self.data.values) if self.data and self.last_update_success else {}
            )
            values.pop((BUNDLE, pid), None)
            if outcome.has_observed_value:
                values[(BUNDLE, pid)] = outcome.observed
            pending = outcome.error in ("readback_failed", "readback_mismatch")
            if pending:
                self._pending_confirmations[pid] = (target, monotonic() + 600)
                self.update_interval = timedelta(seconds=15)
            self.control_write_status[pid] = (
                "awaiting_confirmation"
                if pending
                else "failed"
                if outcome.error
                else "confirmed"
            )
            self.async_set_updated_data(Snapshot(values))
            if outcome.error and not pending:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key=outcome.error
                )
            return {"parameter_id": pid, "write_status": self.control_write_status[pid]}
