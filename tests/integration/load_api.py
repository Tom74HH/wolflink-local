"""Load HA-independent implementation modules without importing HA's entrypoint.

This does not replace or mock Home Assistant classes. HA-specific tests import
the actual custom_components package separately in a Home Assistant environment.
"""

from pathlib import Path
import sys
from types import ModuleType

NAME = "wolflink_test_api"
if NAME not in sys.modules:
    package = ModuleType(NAME)
    package.__path__ = [
        str(Path(__file__).resolve().parents[2] / "custom_components/wolflink_local")
    ]
    sys.modules[NAME] = package

from wolflink_test_api.api import Definition, Snapshot
from wolflink_test_api.controls import (
    CONTROLS,
    DAILY_IDS,
    FUTURE_IDS,
    ParameterMeta,
    WolfError,
    decimal_value,
    user_metadata,
    validate_write,
)
