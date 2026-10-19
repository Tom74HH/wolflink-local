"""Shared local transport snapshots and write results; no cloud client."""
from dataclasses import dataclass, field
from typing import Any
from .models import Parameter
from .controls import ParameterMeta
_MISSING = object()

@dataclass
class Definition:
    sensors: list[Parameter]
    metadata: dict[int, ParameterMeta]


@dataclass
class Snapshot:
    # Keys include bundle to prevent an expert-context duplicate replacing user data.
    values: dict[tuple[int, int], Any] = field(default_factory=dict)


@dataclass
class WriteOutcome:
    metadata: dict[int, ParameterMeta]
    observed: Any = _MISSING
    error: str | None = None

    @property
    def has_observed_value(self):
        return self.observed is not _MISSING

