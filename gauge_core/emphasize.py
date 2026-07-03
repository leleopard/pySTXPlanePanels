"""Shared helper for split-font-size numeric readouts.

Used by both the `Text` component and `VectorTape` labels: a numeric
readout where the last few digits render at a different (usually
smaller) font size than the leading digits — the common glass-cockpit
altimeter convention, e.g. 30,000 ft shown as a big "30" followed by a
smaller "000".
"""

from __future__ import annotations


def split_at_place(value: float, digits: float) -> tuple[str, str]:
    """Split `value` into (hi_text, lo_text) at the given trailing-digit count.

    `digits` is how many trailing digits render as the "lo" (de-emphasized)
    part — not a place *value* — so it works for any count, not just clean
    powers of ten: digits=3 -> ("30", "000") for 30000, digits=2 ->
    ("84", "00") for 8400, digits=1 -> ("840", "0") for 8400, digits=0 ->
    ("8400", "") (nothing de-emphasized, the whole value is "hi").

    `lo_text` is always zero-padded to `digits` characters.
    """
    digit_count = int(digits)
    place = 10 ** digit_count
    v_int = int(round(value))
    hi, lo = divmod(v_int, place)
    lo_text = f"{lo:0{digit_count}d}" if digit_count > 0 else ""
    return str(hi), lo_text
