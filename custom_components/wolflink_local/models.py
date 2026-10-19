"""Local device and parameter records, independent of cloud libraries."""
from dataclasses import dataclass


@dataclass
class Device:
    id: int
    gateway: int
    name: str

    def __init__(self, device_id, gateway, name, system_share_id=None):
        self.id, self.gateway, self.name = device_id, gateway, name


@dataclass
class Parameter:
    value_id: int
    name: str
    parent: str
    parameter_id: int
    bundle_id: int
    read_only: bool

    def convert_raw_value(self, value):
        return value


class SimpleParameter(Parameter):
    pass


class Temperature(Parameter):
    unit = "°C"


class Pressure(Parameter):
    unit = "bar"


class PercentageParameter(Parameter):
    unit = "%"


class HoursParameter(Parameter):
    unit = "h"


class EnergyParameter(Parameter):
    unit = "kWh"


class PowerParameter(Parameter):
    unit = "kW"


class RPMParameter(Parameter):
    unit = "rpm"


class FlowParameter(Parameter):
    unit = "l/min"


class FrequencyParameter(Parameter):
    unit = "Hz"


@dataclass
class ListItem:
    value: int
    name: str


@dataclass
class ListItemParameter(Parameter):
    items: list[ListItem]

    def __init__(self, value_id, name, parent, items, parameter_id, bundle_id, read_only):
        super().__init__(value_id, name, parent, parameter_id, bundle_id, read_only)
        self.items = items
