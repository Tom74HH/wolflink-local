"""Explicit Save/Stop actions for WOLF party and holiday periods."""

from datetime import datetime
import asyncio
from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .controls import BUNDLE, WolfError
from .api import Snapshot
from .entity import WolfEntity
from .mode_drafts import draft, local_now
from .timed_modes import MODES


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        TimedModeButton(c, mode, activate)
        for c in entry.runtime_data.coordinators
        for mode, (pid, _, _) in MODES.items()
        if pid in c.definition.metadata
        for activate in (True, False)
    )


class TimedModeButton(WolfEntity, ButtonEntity):
    def __init__(self, coordinator, mode, activate):
        super().__init__(coordinator, MODES[mode][0], "start" if activate else "stop")
        self.mode, self.activate = mode, activate
        self._attr_translation_key = mode + ("_save" if activate else "_stop")
        self._attr_icon = "mdi:content-save" if activate else "mdi:stop-circle-outline"

    @property
    def available(self):
        return super().available and not self.coordinator.read_only

    async def async_press(self):
        async with self.coordinator.timed_mode_lock:
            await self._async_press_locked()

    async def _async_press_locked(self):
        values = draft(self.coordinator)
        start = local_now() if self.mode == "party" else values["holiday_start"]
        end = (
            datetime.fromtimestamp(
                start.timestamp() + values["party_minutes"] * 60, start.tzinfo
            )
            if self.mode == "party"
            else values["holiday_end"]
        )
        self.coordinator._set_write_status(self.parameter_id, "sending")
        try:
            observed = await self.coordinator.api.set_timed_mode(
                self.coordinator.device,
                self.mode,
                start,
                end,
                local_now,
                lambda: self.coordinator.read_only,
                activate=self.activate,
                progress=lambda status: self.coordinator._set_write_status(
                    self.parameter_id, status
                ),
            )
            if isinstance(observed, str) and observed in ("0", "1"):
                values = (
                    dict(self.coordinator.data.values)
                    if self.coordinator.data and self.coordinator.last_update_success
                    else {}
                )
                values[(BUNDLE, self.parameter_id)] = observed
                self.coordinator.async_set_updated_data(Snapshot(values))
            self.coordinator._set_write_status(self.parameter_id, "confirmed")
        except WolfError as exc:
            self.coordinator._set_write_status(self.parameter_id, "failed")
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key=exc.code
            ) from None
        except asyncio.CancelledError:
            self.coordinator._set_write_status(self.parameter_id, "failed")
            raise
        except Exception:
            self.coordinator._set_write_status(self.parameter_id, "failed")
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="write_failed"
            ) from None
        finally:
            await self.coordinator.async_request_refresh()
