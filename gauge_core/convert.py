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

    Q and R (RREF datarefs) arrive in deg/s, so the formula output is already
    deg/s — no unit conversion needed. The original pyXPPanels code read from
    DATA group 16 which sent angular rates in rad/s and applied * 180/pi;
    that factor must be omitted here.
    """
    pitch = math.radians(get("sim/flightmodel/position/theta"))
    roll = math.radians(get("sim/flightmodel/position/phi"))
    Q = get("sim/flightmodel/position/Q")  # pitch rate, deg/s
    R = get("sim/flightmodel/position/R")  # yaw rate, deg/s

    cos_pitch = math.cos(pitch)
    if cos_pitch == 0:
        return 0.0
    return Q * math.sin(roll) / cos_pitch + R * math.cos(roll) / cos_pitch


# -- Altitude display ----------------------------------------------------

def return_alt_hundreds(value: float, _get: GetData) -> float:
    """Altitude in hundreds of feet (truncated). Used by transponder FL display."""
    return float(int(value / 100))


# -- Predicates -----------------------------------------------------------
# Predicates return a bool. Used by visibility transforms and
# (potentially) for state-dependent component swapping.

def true_if_over_zero(value: float, _get: GetData) -> bool:
    return value > 0.0

def true_if_zero(value: float, _get: GetData) -> bool:
    return value == 0.0

def true_if_equals_1(value: float, _get: GetData) -> bool:
    return value == 1.0

def true_if_equals_2(value: float, _get: GetData) -> bool:
    return value == 2.0

def true_if_equals_3(value: float, _get: GetData) -> bool:
    return value == 3.0

def true_if_equals_4(value: float, _get: GetData) -> bool:
    return value == 4.0

def true_if_equals_5(value: float, _get: GetData) -> bool:
    return value == 5.0

def true_if_over_1(value: float, _get: GetData) -> bool:
    return value > 1.0

def true_if_over_2(value: float, _get: GetData) -> bool:
    return value > 2.0


# -- Fuel / engine conversion --------------------------------------------

def convert_lbs_to_gallons(value: float, _get: GetData) -> float:
    """Convert fuel weight in lbs to US gallons (avgas ≈ 6 lbs/gal)."""
    return value / 6.0


def convert_suction(value: float, _get: GetData) -> float:
    """Scale vacuum suction reading (matches original pyXPPanels convertSuction)."""
    return value * 2.8


# -- VOR / NAV predicates ------------------------------------------------

def nav_gsflg_visible(value: float, _get: GetData) -> bool:
    """GS flag visible when GS is not valid (original: value != 10)."""
    return int(value) != 10


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
    "return_alt_hundreds": return_alt_hundreds,
    "true_if_over_zero": true_if_over_zero,
    "true_if_zero": true_if_zero,
    "true_if_equals_1": true_if_equals_1,
    "true_if_equals_2": true_if_equals_2,
    "true_if_equals_3": true_if_equals_3,
    "true_if_equals_4": true_if_equals_4,
    "true_if_equals_5": true_if_equals_5,
    "true_if_over_1": true_if_over_1,
    "true_if_over_2": true_if_over_2,
    "convert_lbs_to_gallons": convert_lbs_to_gallons,
    "convert_suction": convert_suction,
    "nav_gsflg_visible": nav_gsflg_visible,
    "identity": identity,
}.items():
    register_convert(_name, _func)
