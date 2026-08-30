# SPDX-License-Identifier: Apache-2.0
"""Quantities: the unit table, conversion, and STATED PRECISION.

The numeric contradiction check is the most valuable thing this package
does for a manual — two values for one named quantity is a defect, full
stop — which makes a false positive here more expensive than anywhere
else. One of those cost this module a rewrite and is worth recording:

    `40 Nm` and `29.5 lb-ft` are THE SAME FIGURE. Converted exactly,
    29.5 lb-ft is 39.99669 Nm, and an equality test with a 1e-6 tolerance
    reported the author's own correct conversion as a contradiction.

The fix is not a looser tolerance picked by taste. **A number carries its
own precision in the way it is written.** `29.5` asserts a value between
29.45 and 29.55; `40` asserts 39.5 to 40.5. Two quantities conflict when
those intervals do not overlap, and agree when they do — which reports
40 Nm against 45 Nm, stays quiet on 40 Nm against 29.5 lb-ft, and needs no
threshold anybody has to justify.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re

#: unit -> (dimension, factor to that dimension's base unit)
UNITS: dict[str, tuple[str, float]] = {}


def _u(dimension: str, table: dict[str, float]) -> None:
    for name, factor in table.items():
        UNITS[name.lower()] = (dimension, factor)


_u("length", {"mm": 0.001, "cm": 0.01, "m": 1, "km": 1000, "in": 0.0254,
              "ft": 0.3048, "yd": 0.9144, "mi": 1609.344, "inch": 0.0254,
              "inches": 0.0254, "metre": 1, "metres": 1, "meter": 1,
              "meters": 1, "thou": 2.54e-5})
_u("mass", {"mg": 1e-6, "g": 0.001, "kg": 1, "t": 1000, "lb": 0.45359237,
            "lbs": 0.45359237, "oz": 0.0283495})
_u("time", {"ms": 0.001, "s": 1, "sec": 1, "secs": 1, "second": 1,
            "seconds": 1, "min": 60, "mins": 60, "minute": 60,
            "minutes": 60, "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600,
            "hours": 3600, "day": 86400, "days": 86400})
_u("torque", {"nm": 1, "n·m": 1, "n-m": 1, "newton-metre": 1,
              "newton-metres": 1, "newton-meter": 1, "lbf-ft": 1.35582,
              "lb-ft": 1.35582, "ft-lb": 1.35582, "ftlb": 1.35582,
              "lbf-in": 0.112985})
_u("pressure", {"pa": 1, "kpa": 1000, "mpa": 1e6, "bar": 1e5,
                "psi": 6894.76, "mbar": 100})
_u("voltage", {"mv": 0.001, "v": 1, "kv": 1000, "volt": 1, "volts": 1})
_u("current", {"ma": 0.001, "a": 1, "amp": 1, "amps": 1, "ampere": 1})
_u("power", {"mw": 0.001, "w": 1, "kw": 1000, "hp": 745.7})
_u("frequency", {"hz": 1, "khz": 1e3, "mhz": 1e6, "ghz": 1e9})
_u("angle", {"deg": 1, "degree": 1, "degrees": 1, "°": 1, "rad": 57.2958})
_u("data", {"b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12,
            "kib": 1024, "mib": 1048576, "gib": 1073741824})
#: Temperature is multiplicative-free: °C and °F do not convert by a
#: factor, so two temperatures are only ever compared in the SAME unit.
#: Pretending otherwise would be a conversion bug wearing a unit table.
_u("temperature", {"°c": 1, "°f": 1, "c": 1, "f": 1, "k": 1})

_UNIT_ALT = sorted(UNITS, key=len, reverse=True)
NUM_UNIT = re.compile(
    r"(?<![\w.])(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>"
    + "|".join(re.escape(u) for u in _UNIT_ALT) + r")(?![A-Za-z0-9])",
    re.I)

#: Words that name a quantity. The key of a numeric claim is one of these
#: plus the dimension, which is what makes "40 Nm" and "45 Nm" comparable
#: and keeps "40 Nm of torque" away from "40 mm of clearance". A number
#: with no quantity word near it is SKIPPED rather than attached to
#: whatever noun was closest -- inventing the subject is how a continuity
#: report fills with conflicts that are really parser noise, and one of
#: those costs more trust than ten real findings buy.
QUANTITY_WORDS = {
    "torque", "pressure", "voltage", "current", "resistance", "power",
    "frequency", "temperature", "speed", "weight", "mass", "length",
    "width", "height", "depth", "diameter", "radius", "thickness",
    "clearance", "gap", "tolerance", "capacity", "volume", "flow",
    "duration", "delay", "timeout", "interval", "range", "altitude",
    "distance", "load", "force", "angle", "offset", "margin", "rating",
    "output", "input", "supply", "drop", "rise", "limit", "setting",
}


def dimension(unit: str) -> str:
    return UNITS[unit.lower()][0] if unit.lower() in UNITS else ""


def to_base(number: float | None, unit: str) -> float | None:
    """Convert to the dimension's base unit. Temperature is left alone."""
    if number is None:
        return None
    key = (unit or "").lower()
    if key not in UNITS:
        return number
    dim, factor = UNITS[key]
    return number if dim == "temperature" else number * factor


def half_ulp(number_text: str) -> float:
    """Half a unit in the last place the number was WRITTEN to.

    `40` -> 0.5, `40.0` -> 0.05, `29.5` -> 0.05, `1,500` -> 0.5. This is
    the whole precision model, and it is deliberately about the text
    rather than the float: an author who wrote `40` did not measure 40.000.
    """
    text = (number_text or "").replace(",", "").strip()
    try:
        decimal = Decimal(text)
    except (InvalidOperation, ValueError):
        return 0.0
    exponent = decimal.as_tuple().exponent
    if not isinstance(exponent, int):
        return 0.0
    return float(Decimal(10) ** exponent) / 2.0


def interval(number_text: str, unit: str) -> tuple[float, float] | None:
    """What the written quantity actually asserts, in base units."""
    text = (number_text or "").replace(",", "").strip()
    try:
        value = float(text)
    except ValueError:
        return None
    base = to_base(value, unit)
    if base is None:
        return None
    slack = half_ulp(text)
    key = (unit or "").lower()
    if key in UNITS and UNITS[key][0] != "temperature":
        slack *= UNITS[key][1]
    return (base - slack, base + slack)


def conflict(a_text: str, a_unit: str, b_text: str,
             b_unit: str) -> bool:
    """Do two stated quantities disagree?

    False when either cannot be read, when the dimensions differ (a naming
    problem, not a value contradiction, and calling it one would be wrong
    twice), or when the stated-precision intervals overlap.
    """
    if dimension(a_unit) != dimension(b_unit):
        return False
    if dimension(a_unit) == "temperature" and \
            (a_unit or "").lower() != (b_unit or "").lower():
        return False
    left = interval(a_text, a_unit)
    right = interval(b_text, b_unit)
    if left is None or right is None:
        return False
    return left[1] < right[0] or right[1] < left[0]


def split_value(text: str) -> tuple[str, str]:
    """`"40 Nm"` -> `("40", "nm")`. `("", "")` when there is no quantity."""
    m = NUM_UNIT.search(text or "")
    if not m:
        m = re.search(r"(?<![\w.])(-?\d[\d,]*(?:\.\d+)?)", text or "")
        return (m.group(1), "") if m else ("", "")
    return m.group("num"), m.group("unit").lower()
