"""Sensor descriptions adapted from Home Assistant 2026.10.1 (Apache-2.0)."""

from collections.abc import Callable
from dataclasses import dataclass

from .models import (
    EnergyParameter,
    FlowParameter,
    FrequencyParameter,
    HoursParameter,
    ListItemParameter,
    Parameter,
    PercentageParameter,
    PowerParameter,
    Pressure,
    RPMParameter,
    SimpleParameter,
    Temperature,
)

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, STATES
from homeassistant.config_entries import ConfigEntry
from .coordinator import WolfLinkCoordinator


def get_listitem_resolve_state(wolf_object: Parameter, state: str) -> str:
    """Resolve list item state."""
    assert isinstance(wolf_object, ListItemParameter)
    try:
        code = int(state)
    except (ValueError, TypeError):
        return str(state)
    resolved_state = [item for item in wolf_object.items if item.value == code]
    if resolved_state:
        resolved_name = resolved_state[0].name
        state = STATES.get(resolved_name, resolved_name)
    return state


@dataclass(kw_only=True, frozen=True)
class WolflinkSensorEntityDescription(SensorEntityDescription):
    """Describes Wolflink sensor entity."""

    value_fn: Callable[[Parameter, str], str | None] = lambda param, value: value
    supported_fn: Callable[[Parameter], bool]


SENSOR_DESCRIPTIONS = [
    WolflinkSensorEntityDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        supported_fn=lambda param: isinstance(param, Temperature),
    ),
    WolflinkSensorEntityDescription(
        key="pressure",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.BAR,
        state_class=SensorStateClass.MEASUREMENT,
        supported_fn=lambda param: isinstance(param, Pressure),
    ),
    WolflinkSensorEntityDescription(
        key="energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        supported_fn=lambda param: isinstance(param, EnergyParameter),
    ),
    WolflinkSensorEntityDescription(
        key="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        supported_fn=lambda param: isinstance(param, PowerParameter),
    ),
    WolflinkSensorEntityDescription(
        key="percentage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        supported_fn=lambda param: isinstance(param, PercentageParameter),
    ),
    WolflinkSensorEntityDescription(
        key="list_item",
        translation_key="state",
        supported_fn=lambda param: isinstance(param, ListItemParameter),
        value_fn=get_listitem_resolve_state,
    ),
    WolflinkSensorEntityDescription(
        key="hours",
        device_class=SensorDeviceClass.DURATION,
        icon="mdi:clock",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        supported_fn=lambda param: isinstance(param, HoursParameter),
    ),
    WolflinkSensorEntityDescription(
        key="flow",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        supported_fn=lambda param: isinstance(param, FlowParameter),
    ),
    WolflinkSensorEntityDescription(
        key="frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        supported_fn=lambda param: isinstance(param, FrequencyParameter),
    ),
    WolflinkSensorEntityDescription(
        key="rpm",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        supported_fn=lambda param: isinstance(param, RPMParameter),
    ),
    WolflinkSensorEntityDescription(
        key="default",
        supported_fn=lambda param: isinstance(param, SimpleParameter),
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up all entries for Wolf Platform."""
    async_add_entities(
        WolfLinkSensor(coordinator, parameter, description)
        for coordinator in config_entry.runtime_data.coordinators
        for parameter in coordinator.parameters
        for description in SENSOR_DESCRIPTIONS
        if description.supported_fn(parameter)
    )
    from .future import DailyScheduleSensor
    from .controls import DAILY_IDS

    async_add_entities(
        DailyScheduleSensor(coordinator, pid)
        for coordinator in config_entry.runtime_data.coordinators
        for pid in DAILY_IDS
        if pid in coordinator.definition.metadata
        and pid not in {p.parameter_id for p in coordinator.parameters}
    )


class WolfLinkSensor(CoordinatorEntity[WolfLinkCoordinator], SensorEntity):
    """Preserve upstream sensor classes while never returning a stale invalid value."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, wolf_object, description):
        super().__init__(coordinator)
        self.entity_description = description
        self.wolf_object = wolf_object
        self._attr_name = wolf_object.name
        self._attr_unique_id = (
            f"{coordinator.device_key}:{wolf_object.parameter_id}:sensor"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_key)},
            manufacturer=MANUFACTURER,
            name=coordinator.device.name,
            configuration_url=f"http://{coordinator.entry.data['host']}/",
        )

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        state = self.coordinator.data.values.get(
            (self.wolf_object.bundle_id, self.wolf_object.parameter_id)
        )
        if state is None:
            return None
        if self.entity_description.key in ("list_item", "default"):
            return self.entity_description.value_fn(self.wolf_object, str(state))
        try:
            from .controls import decimal_value

            return float(decimal_value(state))
        except Exception:
            return None

    @property
    def available(self):
        return super().available and self.native_value is not None

    @property
    def extra_state_attributes(self):
        meta = self.coordinator.definition.metadata.get(self.wolf_object.parameter_id)
        return {
            "parameter_id": self.wolf_object.parameter_id,
            "value_id": meta.value_id if meta else self.wolf_object.value_id,
            "parent": self.wolf_object.parent,
            "write_status": self.coordinator.control_write_status.get(
                self.wolf_object.parameter_id, "reported"
            ),
        }
