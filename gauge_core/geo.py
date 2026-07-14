"""Small geographic helpers for lat/lon-driven components (e.g. the
VectorCompassRose moving map).

Uses a flat-earth (equirectangular) approximation, not full great-circle
math — accurate enough for HSI-scale ranges (tens to low hundreds of NM)
and much cheaper than haversine, which is all a cockpit gauge needs.
"""

from __future__ import annotations

import math

_NM_PER_DEG_LAT = 60.0


def bearing_distance_nm(
    lat1: float, lon1: float, lat2: float, lon2: float,
) -> tuple[float, float]:
    """Return (bearing_deg, distance_nm) from point 1 to point 2.

    bearing_deg is a compass bearing (0 = north, clockwise positive),
    matching the convention every other rotating element in
    VectorCompassRose already uses with `_point_at()`.
    """
    dlat_nm = (lat2 - lat1) * _NM_PER_DEG_LAT
    dlon_nm = (lon2 - lon1) * _NM_PER_DEG_LAT * math.cos(math.radians(lat1))
    distance_nm = math.hypot(dlat_nm, dlon_nm)
    bearing_deg = math.degrees(math.atan2(dlon_nm, dlat_nm)) % 360.0
    return bearing_deg, distance_nm
