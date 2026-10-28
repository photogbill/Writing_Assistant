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

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

#: unit -> (dimension, factor to that dimension's base unit). Matched
#: WITHOUT regard to case.
UNITS: dict[str, tuple[str, float]] = {}

#: Units whose CASE carries meaning, matched exactly as written. Measured
#: 2026-10-28: with every unit case-folded, `1 MW` read as one milliwatt and
#: so "conflicted" with `1000 kW`, while `10 mW` and `10 MW` agreed; `10 kΩ`
#: was read as ten kelvin; "5 a day" was five amps and "item 5 b" five
#: bytes. A milli- and a mega- prefix differ only in case, and so do kelvin
#: and the word "k".
CASED: dict[str, tuple[str, float]] = {}


def _u(dimension: str, table: dict[str, float]) -> None:
    for name, factor in table.items():
        UNITS[name.lower()] = (dimension, factor)


def _c(dimension: str, table: dict[str, float]) -> None:
    for name, factor in table.items():
        CASED[name] = (dimension, factor)


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
_c("pressure", {"MPa": 1e6, "mPa": 1e-3})
_u("voltage", {"mv": 0.001, "v": 1, "kv": 1000, "volt": 1, "volts": 1})
_c("voltage", {"mV": 1e-3, "MV": 1e6})
_u("current", {"ma": 0.001, "amp": 1, "amps": 1, "ampere": 1, "amperes": 1})
_c("current", {"A": 1, "mA": 1e-3, "kA": 1e3})
_u("power", {"mw": 0.001, "w": 1, "kw": 1000, "hp": 745.7})
_c("power", {"mW": 1e-3, "MW": 1e6, "kW": 1e3})
_u("frequency", {"hz": 1, "khz": 1e3, "mhz": 1e6, "ghz": 1e9})
_c("frequency", {"mHz": 1e-3, "MHz": 1e6})
_u("angle", {"deg": 1, "degree": 1, "degrees": 1, "°": 1, "rad": 57.2958})
_u("data", {"kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12,
            "kib": 1024, "mib": 1048576, "gib": 1073741824})
_c("data", {"B": 1})
_u("resistance", {"ohm": 1, "ohms": 1, "kohm": 1e3, "kohms": 1e3})
_c("resistance", {"Ω": 1, "kΩ": 1e3, "MΩ": 1e6, "mΩ": 1e-3})
#: Temperature is multiplicative-free: °C and °F do not convert by a
#: factor, so two temperatures are only ever compared in the SAME unit.
#: Pretending otherwise would be a conversion bug wearing a unit table.
#: Bare C, F and K count only in capitals ("20 C"), never "c" or "k".
_u("temperature", {"°c": 1, "°f": 1, "°k": 1})
_c("temperature", {"C": 1, "F": 1, "K": 1})


def _resolve(unit: str) -> tuple[str, float] | None:
    """The (dimension, factor) a unit AS WRITTEN stands for."""
    if unit in CASED:
        return CASED[unit]
    return UNITS.get((unit or "").lower())


def _alternative(name: str, cased: bool) -> str:
    body = re.escape(name)
    if not cased:
        body = f"(?i:{body})"
    if name.lower() == "in":
        # "12 in" is twelve inches; "steps 1 to 5 in order" is not.
        body += r"(?![ \t]+[A-Za-z0-9])"
    return body


_ALT = sorted([(n, False) for n in UNITS] + [(n, True) for n in CASED],
              key=lambda pair: len(pair[0]), reverse=True)
NUM_UNIT = re.compile(
    r"(?<![\w.])(?<!\d\s)(?P<num>[-−]?\d[\d,]*(?:\.\d+)?)\s*(?P<unit>"
    + "|".join(_alternative(n, c) for n, c in _ALT)
    + r")(?![A-Za-z0-9])")

#: A range written before a quantity: "10–20 Nm", "10 - 20 Nm", "10 to 20".
_RANGE_LOW = re.compile(
    r"(?<![\w.])(?P<low>[-−]?\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<lowunit>[^\W\d_]{1,8}|°[CFK]?|Ω)?"
    r"\s*(?:–|—|-|to)\s*$")
_CHAIN = re.compile(r"\d\s*(?:–|—|-|to)\s*$")


def _range_low(before: str, unit: str):
    """The low end of a range ending where `before` ends, or None.

    A word between the low number and "to" must be a UNIT of the same
    dimension — "40 Nm to 50 Nm". It used to be any word, so "Tighten the
    4 bolts to 40 Nm" was a 4–40 Nm range that lost its object, and "Heat 3
    cups to 180 °C" was 3–180 °C; a range that wide overlaps everything and
    hid real contradictions. "bolts 1 to 6 to 25 Nm" is a chain, not a
    range of torques.
    """
    m = _RANGE_LOW.search(before)
    if not m or m.end() != len(before):
        return None
    word = m.group("lowunit")
    if word and dimension(word) != dimension(unit):
        return None
    if _CHAIN.search(before[:m.start()]):
        return None
    return m

#: The word for a dimension, when a quantity is only named by its verb:
#: "Tighten the wheel nuts to 110 Nm" is a torque.
DIMENSION_WORD = {
    "torque": "torque", "pressure": "pressure", "voltage": "voltage",
    "current": "current", "power": "power", "frequency": "frequency",
    "temperature": "temperature", "length": "length", "mass": "mass",
    "time": "duration", "angle": "angle", "resistance": "resistance",
    "data": "size",
}

#: Words that name a quantity. A number with no quantity word near it —
#: and no imperative naming what it is set on — is SKIPPED rather than
#: attached to whatever noun was closest: inventing the subject is how a
#: continuity report fills with conflicts that are really parser noise,
#: and one of those costs more trust than ten real findings buy.
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
    found = _resolve(unit or "")
    return found[0] if found else ""


def to_base(number: float | None, unit: str) -> float | None:
    """Convert to the dimension's base unit. Temperature is left alone."""
    if number is None:
        return None
    found = _resolve(unit or "")
    if found is None:
        return number
    dim, factor = found
    return number if dim == "temperature" else number * factor


def _number(text: str) -> str:
    return (text or "").replace(",", "").replace("−", "-").strip()


def half_ulp(number_text: str) -> float:
    """Half a unit in the last place the number was WRITTEN to.

    `40` -> 0.5, `40.0` -> 0.05, `29.5` -> 0.05, `1,500` -> 0.5. This is
    the whole precision model, and it is deliberately about the text
    rather than the float: an author who wrote `40` did not measure 40.000.
    """
    text = _number(number_text)
    try:
        decimal = Decimal(text)
    except (InvalidOperation, ValueError):
        return 0.0
    exponent = decimal.as_tuple().exponent
    if not isinstance(exponent, int):
        return 0.0
    return float(Decimal(10) ** exponent) / 2.0


def _bounds_of(number_text: str) -> tuple[str, str]:
    """`"10–20"` -> ("10", "20"); `"40"` -> ("40", "40")."""
    text = (number_text or "").strip()
    m = re.fullmatch(r"([-−]?\d[\d,]*(?:\.\d+)?)\s*(?:–|—|-|to)\s*"
                     r"([-−]?\d[\d,]*(?:\.\d+)?)", text)
    if m:
        return m.group(1), m.group(2)
    return text, text


def interval(number_text: str, unit: str) -> tuple[float, float] | None:
    """What the written quantity actually asserts, in base units. A range
    ("10–20") asserts everything from its low end to its high end."""
    low_text, high_text = _bounds_of(number_text)
    try:
        low, high = float(_number(low_text)), float(_number(high_text))
    except ValueError:
        return None
    lo, hi = to_base(min(low, high), unit), to_base(max(low, high), unit)
    if lo is None or hi is None:
        return None
    found = _resolve(unit or "")
    factor = found[1] if found and found[0] != "temperature" else 1.0
    return (lo - half_ulp(low_text) * factor, hi + half_ulp(high_text) * factor)


def unit_key(unit: str) -> tuple[str, str] | None:
    """What makes two units THE SAME unit: dimension and factor, except
    for temperature, where every unit has factor 1 and °C, °F and K are
    different scales. Keyed by factor alone, 20 °C and 68 °F were "the
    same unit" compared as raw numbers — a certain contradiction."""
    found = _resolve(unit or "")
    if found is None:
        return None
    dim, factor = found
    if dim == "temperature":
        return dim, (unit or "").lstrip("°").strip()[:1].upper()
    return dim, repr(float(factor))


def _same_unit(a_unit: str, b_unit: str) -> bool:
    a = unit_key(a_unit)
    return a is not None and a == unit_key(b_unit)


def conflict(a_text: str, a_unit: str, b_text: str,
             b_unit: str) -> bool:
    """Do two stated quantities disagree?

    False when either cannot be read, when the dimensions differ (a naming
    problem, not a value contradiction, and calling it one would be wrong
    twice), or when the stated-precision intervals overlap.

    IN THE SAME UNIT, THE NUMBERS ARE COMPARED AS WRITTEN (2026-10-28).
    The precision intervals exist for the author's own CONVERSIONS — 40 Nm
    against 29.5 lb-ft. Applied within one unit they hid real
    contradictions: `3 V` asserted 2.5–3.5 V and so "agreed" with `3.3 V`,
    and `1 kg` agreed with `1.4 kg`. Nobody writes 3 V meaning 3.3 V.
    """
    if dimension(a_unit) != dimension(b_unit) or not dimension(a_unit):
        return False
    if dimension(a_unit) == "temperature" and not _same_unit(a_unit, b_unit):
        return False
    if _same_unit(a_unit, b_unit):
        a_lo, a_hi = _bounds_of(a_text)
        b_lo, b_hi = _bounds_of(b_text)
        try:
            a_lo, a_hi = Decimal(_number(a_lo)), Decimal(_number(a_hi))
            b_lo, b_hi = Decimal(_number(b_lo)), Decimal(_number(b_hi))
        except (InvalidOperation, ValueError):
            return False
        a_lo, a_hi = min(a_lo, a_hi), max(a_lo, a_hi)
        b_lo, b_hi = min(b_lo, b_hi), max(b_lo, b_hi)
        return a_hi < b_lo or b_hi < a_lo
    left = interval(a_text, a_unit)
    right = interval(b_text, b_unit)
    if left is None or right is None:
        return False
    return left[1] < right[0] or right[1] < left[0]


def split_value(text: str) -> tuple[str, str]:
    """`"40 Nm"` -> `("40", "Nm")`; `"10–20 Nm"` -> `("10–20", "Nm")`.
    `("", "")` when there is no quantity. The unit comes back AS WRITTEN —
    its case can be the difference between milli and mega — and every
    function here resolves it the same way."""
    m = NUM_UNIT.search(text or "")
    if not m:
        m = re.search(r"(?<![\w.])([-−]?\d[\d,]*(?:\.\d+)?)", text or "")
        return (m.group(1), "") if m else ("", "")
    low = _range_low((text or "")[:m.start()], m.group("unit"))
    num = m.group("num")
    if low:
        num = f"{low.group('low')}–{num}"
    return num, m.group("unit")


# ---------------------------------------------------------------------------
# reading quantities out of prose — ONE reader for the Codex and for craft
# ---------------------------------------------------------------------------

@dataclass
class Quantity:
    """One stated quantity, and what it is a quantity OF."""

    start: int
    end: int
    text: str                 # "110 Nm", "10–20 Nm"
    number: str               # "110", "10–20"
    unit: str                 # as written
    dimension: str
    quantity: str             # "torque"
    object: str = ""          # "wheel nuts" — "" when nothing names one

    @property
    def subject(self) -> str:
        return self.object or self.quantity

    @property
    def predicate(self) -> str:
        return self.quantity if self.object else "value"

    @property
    def key(self) -> str:
        """What two quantities must share to be compared at all."""
        return f"{_singular(self.object)}|{self.quantity}|{self.dimension}"


#: Words that end a noun phrase when walking back from a quantity word.
_NP_STOP = {
    "the", "a", "an", "each", "every", "all", "both", "any", "this", "that",
    "these", "those", "its", "their", "our", "your", "is", "are", "was",
    "were", "be", "been", "should", "must", "shall", "will", "can", "may",
    "to", "for", "of", "on", "in", "at", "by", "with", "from", "and", "or",
    "set", "check", "adjust", "tighten", "torque", "apply", "use", "fit",
    "if", "when", "then", "than", "not", "no", "max", "maximum", "min",
    "minimum", "nominal", "rated", "about", "approximately", "between",
}

#: Imperatives a procedure states a value with: "Tighten the wheel nuts to
#: 110 Nm", "Set the gap to 0.8 mm", "Fill the reservoir to 2 l".
IMPERATIVES = {
    "tighten", "torque", "set", "adjust", "fill", "charge", "inflate",
    "pressurise", "pressurize", "preheat", "heat", "cool", "cut", "drill",
    "gap", "space", "trim", "shim", "bleed", "pump", "rate", "limit",
    "calibrate", "regulate", "load", "raise", "lower", "reduce", "increase",
    "apply",
}

#: Words that QUALIFY a quantity rather than name one: "the torque range",
#: "the voltage limit". The quantity is the word before them, kept with the
#: qualifier so a range is not compared with a single figure by accident.
QUALIFIERS = {"range", "limit", "setting", "rating", "tolerance", "margin"}

_WORD = re.compile(r"[A-Za-z][\w'’-]*")


def _singular(phrase: str) -> str:
    words = (phrase or "").lower().split()
    if not words:
        return ""
    last = words[-1]
    if last.endswith("ies") and len(last) > 4:
        last = last[:-3] + "y"
    elif last.endswith("s") and not last.endswith(("ss", "us", "is")):
        last = last[:-1]
    return " ".join(words[:-1] + [last])


def _np_before(words: list[str], index: int) -> str:
    """Up to three words of noun phrase ending just before `index`."""
    out: list[str] = []
    k = index - 1
    while k >= 0 and len(out) < 3:
        w = words[k].lower()
        if w in _NP_STOP or w in QUANTITY_WORDS or not w.isalpha():
            break
        out.insert(0, w)
        k -= 1
    return " ".join(out)


def _np_after(words: list[str], index: int) -> str:
    """Up to three words of noun phrase starting at `index`, past one
    determiner, stopping at a preposition or a quantity word."""
    k = index
    if k < len(words) and words[k].lower() in {"the", "a", "an", "each",
                                               "every", "all", "both"}:
        k += 1
    out: list[str] = []
    while k < len(words) and len(out) < 3:
        w = words[k].lower()
        if w in _NP_STOP or not w.replace("-", "").isalpha():
            break
        out.append(w)
        k += 1
    return " ".join(out)


def _sentence_bounds(prose: str, start: int, end: int) -> tuple[int, int]:
    """The sentence around a quantity. A single newline is a re-wrap, not a
    sentence end ("the torque for the lid⏎bolts is 40 Nm"); a blank line
    is. A full stop between two digits is a decimal point."""
    def is_end(i: int) -> bool:
        ch = prose[i]
        if ch in "!?":
            return True
        if ch == ".":
            return not (0 < i < len(prose) - 1 and prose[i - 1].isdigit()
                        and prose[i + 1].isdigit())
        return ch == "\n" and (prose[i - 1:i] == "\n"
                               or prose[i + 1:i + 2] == "\n")
    left, floor = start - 1, max(-1, start - 400)
    while left > floor and not is_end(left):
        left -= 1
    right, ceiling = end, min(len(prose), end + 400)
    while right < ceiling and not is_end(right):
        right += 1
    return left + 1, right


def quantities(prose: str, extra: set[str] | None = None) -> list[Quantity]:
    """Every stated quantity in a passage of prose, named if it can be.

    THE QUANTITY WORD ALONE WAS THE KEY until 2026-10-28, so every torque in
    a manual was "torque": wheel nuts at 110 Nm and spark plugs at 25 Nm
    were reported as a CERTAIN contradiction, and a 3.3 V logic supply
    "contradicted" a 12 V main supply. Any real service manual tripped it,
    which made the check the tool's most valuable one noise.

    So a quantity is now named by what it belongs to — the noun phrase in
    "the torque for the wheel nuts", "the logic supply", "tighten the wheel
    nuts to" — and only quantities with the SAME object are compared. A
    quantity nothing names keeps its bare word and is compared only within
    its own section (see `contradictions` and the craft `units` check).

    And the imperative a procedure actually uses — "Tighten the wheel nuts
    to 110 Nm" — is read at all: before, it named no quantity word and the
    commonest way of writing a spec produced no claim.
    """
    extra = extra or set()
    out: list[Quantity] = []
    for m in NUM_UNIT.finditer(prose):
        unit = m.group("unit")
        dim = dimension(unit)
        if not dim:
            continue
        number = m.group("num")
        start = m.start()
        window = prose[max(0, start - 24):start]
        low = _range_low(window, unit)
        if low:
            number = f"{low.group('low')}–{number}"
            start = max(0, start - 24) + low.start()
        s_start, s_end = _sentence_bounds(prose, start, m.end())
        before_text = prose[s_start:start]
        after_text = re.split(r"[,;:]|\bthen\b", prose[m.end():s_end],
                              maxsplit=1)[0]
        before = [w.group(0) for w in _WORD.finditer(before_text)]
        after = [w.group(0) for w in _WORD.finditer(after_text)]
        lower_before = [w.lower().replace("’", "'") for w in before]

        quantity, q_index = "", -1
        for k in range(len(lower_before) - 1,
                       max(-1, len(lower_before) - 7), -1):
            if lower_before[k] in QUANTITY_WORDS or lower_before[k] in extra:
                quantity, q_index = lower_before[k], k
                break
        if quantity in QUALIFIERS and q_index > 0 and \
                lower_before[q_index - 1] in QUANTITY_WORDS:
            quantity = f"{lower_before[q_index - 1]} {quantity}"
            q_index -= 1
        if not quantity:
            for w in after[:5]:
                if w.lower() in QUANTITY_WORDS or w.lower() in extra:
                    quantity = w.lower()
                    break

        obj = ""
        verb_first = bool(lower_before) and lower_before[0] in IMPERATIVES
        if q_index >= 0:
            # "the torque for/of (the) X is", else "the X torque is"
            tail = lower_before[q_index + 1:]
            if tail and tail[0] in ("for", "of", "on"):
                obj = _np_after(lower_before, q_index + 2)
            if not obj:
                obj = _np_before(lower_before, q_index)
        if verb_first and not obj:
            # "Tighten the wheel nuts to 110 Nm" / "Set the supply voltage
            # to 12 V": the phrase between the verb and "to".
            try:
                to = len(lower_before) - 1 - lower_before[::-1].index("to")
            except ValueError:
                to = -1
            if to > 0:
                phrase = _np_after(lower_before, 1)
                words = phrase.split()
                if words and words[-1] in QUANTITY_WORDS:
                    quantity = quantity or words[-1]
                    words = words[:-1]
                obj = " ".join(words)
            elif not lower_before[1:] and after:
                # "Apply 40 Nm to the lid bolts."
                lower_after = [w.lower() for w in after]
                if lower_after[0] in ("to", "on", "for"):
                    obj = _np_after(lower_after, 1)
            if not quantity:
                quantity = DIMENSION_WORD.get(dim, "")
        if quantity and not obj and after:
            # "a torque of 45 Nm on the cover", "40 Nm applies to the housing"
            lower_after = [w.lower() for w in after]
            if lower_after[:2] in (["applies", "to"], ["is", "applied"]):
                lower_after = lower_after[2:]
                if lower_after[:1] == ["to"]:
                    lower_after = lower_after[1:]
                obj = _np_after(lower_after, 0)
            elif lower_after[0] in ("on", "to", "for") and not re.match(
                    r"\s*(?:on|to|for)\s+[-−]?\d", after_text, re.I):
                obj = _np_after(lower_after, 1)
        if not quantity:
            continue
        out.append(Quantity(start=start, end=m.end(),
                            text=prose[start:m.end()].strip(),
                            number=number, unit=unit, dimension=dim,
                            quantity=quantity, object=obj))
    # "40 Nm to 50 Nm" is ONE range: drop the low end read on its own.
    ranges = [(q.start, q.end) for q in out if "–" in q.number]
    return [q for q in out if not any(
        a <= q.start and q.end <= b and (q.start, q.end) != (a, b)
        for a, b in ranges)]
