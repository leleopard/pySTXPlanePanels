"""Convert functions for shaping dataref values before they hit a calibration table.

Functions are registered by name so YAML can reference them as plain strings
(e.g. `convert_function: return100s`). Each function receives the raw value
from the dataref plus a `get_data` callable that lets it fetch other
datarefs (used for compound calculations like turn rate).

Behaviour intentionally mirrors `pyXPPanels/lib/general/conversionFunctions.py`
so existing calibration tables port without retuning.
"""

from __future__ import annotations

import math
from typing import Callable

from gauge_core.registry import register_convert


GetData = Callable[[object], float]


# -- Altitude needles ------------------------------------------------------
# Modulo trick that lifts the 100s, 1000s, 10000s digit out of an altitude in
# feet and re-expresses it as a 0..1 fraction so the same [0,0]..[1,360] table
# wraps the needle correctly.

def return100s(value: float, _get: GetData) -> float:
    return (value / 1000.0) % 1.0


def return1000s(value: float, _get: GetData) -> float:
    return (value / 10000.0) % 1.0


def return10000s(value: float, _get: GetData) -> float:
    return (value / 100000.0) % 1.0


# -- Pressure -------------------------------------------------------------

def convert_in_to_mb(value: float, _get: GetData) -> float:
    return value * 33.863753


# -- Radio frequency display ---------------------------------------------
# X-Plane reports COM/NAV frequencies in hundredths of MHz (e.g. 11825 for
# 118.250 MHz). The radios display them divided by 100.

def divideby100(value: float, _get: GetData) -> float:
    return float(value) / 100.0


# -- Compass / heading bug -----------------------------------------------

def add_compass_heading_to_value(value: float, get: GetData) -> float:
    """Bug-relative heading: subtract current heading from the bug setting."""
    heading = get("sim/cockpit2/gauges/indicators/heading_vacuum_deg_mag_pilot[0]")
    bug = value - heading
    if bug < 0:
        bug += 360.0
    return bug


# -- Turn rate (derived from pitch/roll/PQR) -----------------------------

def calculate_turn_rate(_value: float, get: GetData) -> float:
    """Turn rate in deg/s, derived from body rates Q/R and pitch/roll attitude.

    Mirrors the original implementation in pyXPPanels conversionFunctions.py.
    Reads X-Plane DATA group 17 (attitude) and group 16 (rates).
    """
    pitch = math.radians(get((17, 0)))
    roll = math.radians(get((17, 1)))
    Q = get((16, 0))
    P = get((16, 1))  # noqa: F841 — kept for parity with original
    R = get((16, 2))

    cos_pitch = math.cos(pitch)
    if cos_pitch == 0:
        return 0.0
    rate = Q * math.sin(roll) / cos_pitch + R * math.cos(roll) / cos_pitch
    return rate * 180.0 / math.pi


# -- Predicates -----------------------------------------------------------
# Predicates return a bool. Used by visibility transforms and
# (potentially) for state-dependent component swapping.

def true_if_over_zero(value: float, _get: GetData) -> bool:
    return value > 0.0


# -- Identity (default) --------------------------------------------------

def identity(value: float, _get: GetData) -> float:
    return value


# -- Registration ---------------------------------------------------------

for _name, _func in {
    "return100s": return100s,
    "return1000s": return1000s,
    "return10000s": return10000s,
    "convert_in_to_mb": convert_in_to_mb,
    "divideby100": divideby100,
    "add_compass_heading_to_value": add_compass_heading_to_value,
    "calculate_turn_rate": calculate_turn_rate,
    "true_if_over_zero": true_if_over_zero,
    "identity": identity,
}.items():
    register_convert(_name, _func)
