"""X-Plane navdata (airports, VORs, NDBs, waypoints/fixes) extraction and
local caching.

Reads directly from the user's own X-Plane install (`earth_nav.dat`,
`apt.dat`, `earth_fix.dat`) to build a small position-only cache for the
VectorCompassRose moving map. Deliberately never bundled or committed to
this repo: `earth_nav.dat`/`earth_fix.dat` carry a Navigraph/Jeppesen
copyright notice, and this is a public repo — the cache only ever exists
locally, generated on-demand via `gauge_designer/navdata_dialog.py`, and
lives outside the project directory entirely (`CACHE_PATH`) so there's no
way to accidentally commit it.

File layout on a typical X-Plane 11 install (confirmed against a real
install this session):
    Resources/default data/earth_nav.dat                        - navaids
    Custom Data/earth_nav.dat                                    - override
    Resources/default data/earth_fix.dat                         - waypoints/fixes
    Custom Data/earth_fix.dat                                     - override
    Resources/default scenery/default apt dat/Earth nav data/apt.dat  - airports
    Custom Scenery/Global Airports/Earth nav data/apt.dat        - override (XP11)
    Global Scenery/Global Airports/Earth nav data/apt.dat        - override (XP12)

Only these default/global layers are read — individually purchased scenery
packs' own apt.dat files are not enumerated (diminishing returns for
dot-on-a-map accuracy, and there's no bounded way to discover them all).
"""

from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Any

from gauge_core.geo import distance_m

CACHE_PATH = Path.home() / ".pySTXPlanePanels" / "navdata_cache.json"

_NAVAID_ROW_TYPES = {"2": "ndb", "3": "vor"}
_AIRPORT_HEADER_CODES = {"1", "16", "17"}

# apt.dat's "airport" rows include a huge number of small/private/unlicensed
# fields that were never assigned a real ICAO code — X-Plane invents an
# ident for these (e.g. "XEG4CM", "X01") so its own map/UI has something to
# show, and the US FAA's local 3-4 char LID scheme shows up too (e.g.
# "00CA"). None of these would ever appear on a real charted EFIS Nav
# Display, which only draws from officially published, ICAO-coded
# aerodromes. A real ICAO location indicator is exactly 4 uppercase
# letters — confirmed against the real cache that this identifies every
# named major airport (EGLL, KJFK, ...) while flagging ~55% of entries as
# local-only identifiers. These are all still real, physical airfields (not
# bad data), so this is exposed as an opt-in filter (`moving_map.airport.
# icao_only` in VectorCompassRose) rather than dropped at parse time —
# every airport stays in the cache either way.
_ICAO_IDENT_RE = re.compile(r"[A-Z]{4}")


def looks_like_icao_ident(ident: str) -> bool:
    return bool(_ICAO_IDENT_RE.fullmatch(ident))


def parse_earth_nav(path: Path) -> list[dict[str, Any]]:
    """Parse earth_nav.dat, keeping only VOR (row 3) and NDB (row 2) rows.

    Row format: row_code lat lon elevation_ft freq range mag_var ident name...
    """
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            code, _, rest = line.strip().partition(" ")
            kind = _NAVAID_ROW_TYPES.get(code)
            if kind is None:
                continue
            parts = line.split(None, 8)
            if len(parts) < 9:
                continue
            try:
                lat = float(parts[1])
                lon = float(parts[2])
                elevation = float(parts[3])
            except ValueError:
                continue
            out.append({
                "type": kind,
                "ident": parts[7],
                "name": parts[8].strip(),
                "lat": lat,
                "lon": lon,
                "elevation": elevation,
            })
    return out


def parse_earth_fix(path: Path) -> list[dict[str, Any]]:
    """Parse earth_fix.dat (waypoints/fixes) — every non-header row is a fix
    entry; there's no row-type code to filter on here, unlike
    earth_nav.dat/apt.dat.

    Row format: lat lon ident airport_or_ENRT icao_region terminal_code.
    The header ("I", the "1101 Version..." line, a blank line) and the "99"
    terminator are skipped naturally by the field-count/float-parse checks
    below, same as they would be by an explicit check — no special-casing
    needed.
    """
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                lat = float(parts[0])
                lon = float(parts[1])
            except ValueError:
                continue
            ident = parts[2]
            out.append({
                "type": "waypoint",
                "ident": ident,
                "name": " ".join(parts[3:]) if len(parts) > 3 else ident,
                "lat": lat,
                "lon": lon,
                "elevation": 0.0,
            })
    return out


# Row types carrying a usable fallback position when an airport's `1302
# datum_lat`/`datum_lon` key-value rows are present but empty (common for
# small/unmodeled fields — confirmed against real apt.dat data: the keys
# exist with no value, so the runway/helipad geometry is the only position
# available). Column index of that row's first lat/lon, after a plain
# whitespace split.
_FALLBACK_ROW_LATLON_COLS = {
    "100": (9, 10),   # land runway: ... end1_number end1_lat end1_lon ...
    "101": (4, 5),    # water runway: width buoys end1_number end1_lat end1_lon ...
                       # (was (3, 4) — that's end1_number, not lat/lon; fixed
                       # while adding the runway-length feature below, which
                       # needed to get this row's exact columns right anyway)
    "102": (2, 3),    # helipad: helipad_id lat lon ...
}

# Both endpoints (not just the first, like the fallback-position table
# above) for the runway-length declutter feature — length is the great-
# circle distance between them. Land (100) and water (101) runways only;
# helipads (102) have no meaningful "length" the same way.
_RUNWAY_ENDPOINT_COLS = {
    "100": ((9, 10), (18, 19)),
    "101": ((4, 5), (7, 8)),
}


def parse_apt_dat(path: Path) -> list[dict[str, Any]]:
    """Parse apt.dat, streaming line-by-line — never loads the (300+ MB)
    file into memory at once. Keeps only the airport header (ident/name/
    elevation, row 1/16/17) plus each land/water runway's (row 100/101)
    two endpoints, used only to compute the airport's longest runway
    length — the rest of runway/taxiway/pavement geometry is skipped
    without being parsed.

    Position prefers `1302 datum_lat`/`datum_lon` (the documented airport
    reference point) but falls back to the first runway/helipad endpoint
    when those keys are present with no value, which is common for small,
    minimally-modeled fields.

    `runway_length_m` is the longest land/water runway at the airport (great-
    circle distance between its two ends), 0.0 if it has none parseable
    (e.g. heliport-only fields) — feeds `moving_map.airport.min_runway_length`,
    a real-EFIS-style declutter-by-size filter (small fields only show up
    once you zoom in), confirmed against a real apt.dat + the user's own
    screenshot: the small-airfield idents cluttering our display but absent
    from the real Zibo ND were all sub-2200m grass/light-GA strips, while
    the one major airport in view (a real ~3500m airport) was on both.

    Every airport apt.dat carries is kept here, including small/private/
    unlicensed fields with non-ICAO identifiers — see `looks_like_icao_ident`
    and `moving_map.airport.icao_only` for filtering those out at render
    time, an opt-in choice rather than a decision made once at parse time.
    """
    out: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    datum_lat = datum_lon = None
    fallback_lat = fallback_lon = None
    max_runway_len = 0.0

    def finalize() -> None:
        nonlocal cur, datum_lat, datum_lon, fallback_lat, fallback_lon, max_runway_len
        if cur is None:
            return
        lat = datum_lat if datum_lat is not None else fallback_lat
        lon = datum_lon if datum_lon is not None else fallback_lon
        if lat is not None and lon is not None:
            cur["lat"] = lat
            cur["lon"] = lon
            cur["runway_length_m"] = max_runway_len
            out.append(cur)
        cur = None
        datum_lat = datum_lon = None
        fallback_lat = fallback_lon = None
        max_runway_len = 0.0

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            code, _, _rest = line.strip().partition(" ")
            if code in _AIRPORT_HEADER_CODES:
                finalize()
                parts = line.split(None, 5)
                if len(parts) < 5:
                    continue
                try:
                    elevation = float(parts[1])
                except ValueError:
                    elevation = 0.0
                ident = parts[4]
                cur = {
                    "type": "airport",
                    "ident": ident,
                    "name": parts[5].strip() if len(parts) > 5 else ident,
                    "elevation": elevation,
                }
            elif code == "1302" and cur is not None:
                kv = line.split(None, 2)
                if len(kv) < 3:
                    continue
                key, val = kv[1], kv[2].strip()
                try:
                    if key == "datum_lat":
                        datum_lat = float(val)
                    elif key == "datum_lon":
                        datum_lon = float(val)
                except ValueError:
                    pass
            elif code in _FALLBACK_ROW_LATLON_COLS and cur is not None:
                parts = line.split()
                if code in _RUNWAY_ENDPOINT_COLS:
                    (a_lat_i, a_lon_i), (b_lat_i, b_lon_i) = _RUNWAY_ENDPOINT_COLS[code]
                    if len(parts) > max(a_lat_i, a_lon_i, b_lat_i, b_lon_i):
                        try:
                            length = distance_m(
                                float(parts[a_lat_i]), float(parts[a_lon_i]),
                                float(parts[b_lat_i]), float(parts[b_lon_i]),
                            )
                            max_runway_len = max(max_runway_len, length)
                        except ValueError:
                            pass
                if fallback_lat is None:
                    lat_idx, lon_idx = _FALLBACK_ROW_LATLON_COLS[code]
                    if len(parts) > lon_idx:
                        try:
                            fallback_lat = float(parts[lat_idx])
                            fallback_lon = float(parts[lon_idx])
                        except ValueError:
                            pass
            elif code == "99":
                break
    finalize()
    return out


def _resolve_earth_nav_path(xplane_root: Path) -> Path | None:
    for candidate in (
        xplane_root / "Custom Data" / "earth_nav.dat",
        xplane_root / "Resources" / "default data" / "earth_nav.dat",
    ):
        if candidate.is_file():
            return candidate
    return None


def _resolve_earth_fix_path(xplane_root: Path) -> Path | None:
    for candidate in (
        xplane_root / "Custom Data" / "earth_fix.dat",
        xplane_root / "Resources" / "default data" / "earth_fix.dat",
    ):
        if candidate.is_file():
            return candidate
    return None


def _resolve_apt_dat_path(xplane_root: Path) -> Path | None:
    for candidate in (
        xplane_root / "Custom Scenery" / "Global Airports" / "Earth nav data" / "apt.dat",
        xplane_root / "Global Scenery" / "Global Airports" / "Earth nav data" / "apt.dat",
        xplane_root / "Resources" / "default scenery" / "default apt dat" / "Earth nav data" / "apt.dat",
    ):
        if candidate.is_file():
            return candidate
    return None


def build_cache(xplane_root: str | Path) -> dict[str, Any]:
    """Parse the user's own X-Plane install and return a cache dict —
    does not write anything; pair with save_cache() to persist."""
    xplane_root = Path(xplane_root)
    navaids: list[dict[str, Any]] = []
    airports: list[dict[str, Any]] = []
    waypoints: list[dict[str, Any]] = []

    nav_path = _resolve_earth_nav_path(xplane_root)
    if nav_path is not None:
        navaids = parse_earth_nav(nav_path)

    apt_path = _resolve_apt_dat_path(xplane_root)
    if apt_path is not None:
        airports = parse_apt_dat(apt_path)

    fix_path = _resolve_earth_fix_path(xplane_root)
    if fix_path is not None:
        waypoints = parse_earth_fix(fix_path)

    return {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "xplane_root": str(xplane_root),
        "navaids": navaids,
        "airports": airports,
        "waypoints": waypoints,
    }


def save_cache(data: dict[str, Any], path: Path = CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_cache(path: Path = CACHE_PATH) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


class NavDataIndex:
    """Cache entries bucketed into 1°×1° lat/lon cells, so a moving map
    doesn't have to scan the whole (tens-of-thousands-of-entries) cache
    every frame — only the handful of cells around the aircraft's current
    position and the currently-selected range."""

    def __init__(self, cache: dict[str, Any]) -> None:
        self._buckets: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for entry in (
            *cache.get("airports", []), *cache.get("navaids", []), *cache.get("waypoints", []),
        ):
            cell = (int(entry["lat"] // 1), int(entry["lon"] // 1))
            self._buckets.setdefault(cell, []).append(entry)

    def nearby(self, lat: float, lon: float, range_nm: float) -> list[dict[str, Any]]:
        """Return every entry within the cell neighbourhood covering
        `range_nm` around (lat, lon) — a cheap superset, not an exact
        distance filter (the caller filters exactly, e.g. via
        geo.bearing_distance_nm, since that also gives the bearing needed
        for on-screen placement)."""
        cell_radius = max(1, math.ceil(range_nm / 60.0))  # 1 deg lat ~= 60 NM
        clat, clon = int(lat // 1), int(lon // 1)
        out: list[dict[str, Any]] = []
        for dlat in range(-cell_radius, cell_radius + 1):
            for dlon in range(-cell_radius, cell_radius + 1):
                out.extend(self._buckets.get((clat + dlat, clon + dlon), ()))
        return out


_index_cache: NavDataIndex | None = None
_index_loaded = False


def get_index() -> NavDataIndex | None:
    """Lazily load the on-disk cache and build its spatial index once per
    process, shared by every VectorCompassRose moving_map instance —
    tens of thousands of entries is cheap to hold in memory once, not
    worth reloading/rebucketing per instrument."""
    global _index_cache, _index_loaded
    if not _index_loaded:
        _index_loaded = True
        cache = load_cache()
        _index_cache = NavDataIndex(cache) if cache else None
    return _index_cache


def reset_index() -> None:
    """Force the next get_index() call to reload from disk — used after
    importing a cache file over the existing one (see navdata_dialog.py),
    so a live process picks up the new data instead of whatever it had
    already lazily loaded and cached in memory."""
    global _index_cache, _index_loaded
    _index_cache = None
    _index_loaded = False
