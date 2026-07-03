"""Shared helper for split-font-size numeric readouts.

Used by both the `Text` component and `VectorTape` labels: a numeric
readout where digits above a given place value render at a different
(usually larger) font size than the digits below it — the common
glass-cockpit altimeter convention, e.g. 30,000 ft shown as a big "30"
followed by a smaller "000".
"""

from __future__ import annotations


def split_at_place(value: float, place: float) -> tuple[str, str]:
    """Split `value` into (hi_text, lo_text) at the given place value.

    `hi_text` is the plain integer string of ``value // place`` (no
    padding). `lo_text` is ``value % place``, zero-padded to the digit
    width implied by `place` (e.g. place=1000 -> 3 digits, "005").

    `place=1` (or any single-digit place) implies zero digits of
    remainder — Python's `{:00d}` still renders a lone "0" rather than
    nothing, which would silently append a spurious digit (8400 -> "8400"
    + "0" = "84000"), so `lo_text` is forced empty in that case: the whole
    value is emphasized, matching what "split at the ones place" means.
    """
    place_int = int(place)
    digits = len(str(place_int)) - 1
    v_int = int(round(value))
    hi, lo = divmod(v_int, place_int)
    lo_text = f"{lo:0{digits}d}" if digits > 0 else ""
    return str(hi), lo_text
