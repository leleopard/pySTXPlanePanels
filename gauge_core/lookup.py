"""Piecewise-linear lookup tables for gauge calibration.

A calibration table maps a raw simulator value (e.g. 75 kt indicated airspeed)
to a transform value (e.g. 105 degrees of needle rotation). Tables are
sorted ascending by input value; values outside the range clamp to the
edges.
"""

from __future__ import annotations


def lookup_piecewise(table: list[list[float]], value: float) -> float:
    """Return a linear interpolation of `value` against `table`.

    `table` is a list of [x, y] pairs, sorted ascending by x. If `value`
    falls below the first x or above the last x, the corresponding y is
    returned (clamped). Equal x values in adjacent rows yield the lower y.
    """
    if not table:
        return 0.0

    if value <= table[0][0]:
        return float(table[0][1])

    for i in range(len(table) - 1):
        x0, y0 = table[i]
        x1, y1 = table[i + 1]
        if x0 <= value <= x1:
            if x1 == x0:
                return float(y0)
            t = (value - x0) / (x1 - x0)
            return float(y0 + t * (y1 - y0))

    return float(table[-1][1])
