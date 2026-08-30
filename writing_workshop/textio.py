# SPDX-License-Identifier: Apache-2.0
"""The text spine: blocks, sentences, words, syllables — all with offsets.

Every measurement in this package runs through here, so one decision made
once protects all of them:

    **MASKING, NOT STRIPPING.** Markdown that is not prose is replaced by
    SPACES of the same length rather than deleted. Offsets therefore stay
    true to the file on disk all the way from a raw manuscript to a finding
    the author clicks on. Stripping would be simpler and would silently
    shift every span in a document the moment it grew a code fence — a class
    of bug that only shows up in the one place it hurts, which is the jump
    from a finding to the line it is about.

The second decision: a markdown TABLE and a CODE FENCE are not prose. Left
in, they turn every sentence-length distribution in a technical manual into
noise — a pipe-delimited row scans as one 40-word sentence with no verb.
`chunk_text` in ATK already keeps tables intact for retrieval, which is the
right call there and the wrong one here; different jobs, different rule.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

# ---------------------------------------------------------------------------
# blocks
# ---------------------------------------------------------------------------

HEADING = "heading"
PARA = "para"
LIST = "list"
ORDERED = "ordered"
CODE = "code"
TABLE = "table"
QUOTE = "quote"
FRONT = "front"
RULE = "rule"

_ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_SETEXT = re.compile(r"^(=+|-{2,})\s*$")
_FENCE = re.compile(r"^\s*(```+|~~~+)")
_BULLET = re.compile(r"^(\s*)([-*+])\s+(.*)$")
_NUMBER = re.compile(r"^(\s*)(\d+)([.)])\s+(.*)$")
_STEP = re.compile(r"^\s*step\s+(\d+)\b[.:)\s]", re.I)
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_HRULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")


@dataclass
class Block:
    """One structural unit of a markdown file, with its file offsets."""

    kind: str
    start: int
    end: int
    text: str
    level: int = 0          # heading level, or list indent depth
    marker: str = ""        # "-", "3.", "###"
    number: int = 0         # ordered-list / "Step N" number
    line: int = 0           # 1-based first line

    @property
    def is_prose(self) -> bool:
        return self.kind in (PARA, LIST, ORDERED, QUOTE)


def scan_blocks(text: str) -> list[Block]:
    """Split a markdown file into blocks, keeping every offset.

    Deliberately a line scanner and not a markdown parser. The failure the
    2023-era code had was `line.startswith('## ')` producing ZERO sections
    and an empty document, silently, for a model that wrote `##Intro`; the
    fix is not a stricter parser but one that never returns nothing — an
    unrecognised line is a paragraph, and a paragraph is always safe.
    """
    blocks: list[Block] = []
    lines: list[tuple[int, str]] = []
    pos = 0
    for raw in text.splitlines(keepends=True):
        lines.append((pos, raw))
        pos += len(raw)

    i = 0
    n = len(lines)
    para_start: int | None = None
    para_end = 0
    para_lines: list[str] = []
    para_line_no = 0

    def flush_para() -> None:
        nonlocal para_start, para_lines
        if para_start is not None and "".join(para_lines).strip():
            blocks.append(Block(PARA, para_start, para_end,
                                "".join(para_lines).rstrip(),
                                line=para_line_no))
        para_start = None
        para_lines = []

    # YAML front matter, but only when the file opens with it
    if n and lines[0][1].rstrip("\r\n") == "---":
        for j in range(1, n):
            if lines[j][1].rstrip("\r\n") in ("---", "..."):
                end = lines[j][0] + len(lines[j][1])
                blocks.append(Block(FRONT, 0, end, text[0:end], line=1))
                i = j + 1
                break

    while i < n:
        start, raw = lines[i]
        stripped = raw.rstrip("\r\n")
        bare = stripped.strip()

        if not bare:
            flush_para()
            i += 1
            continue

        fence = _FENCE.match(stripped)
        if fence:
            flush_para()
            token = fence.group(1)[:3]
            j = i + 1
            while j < n and not lines[j][1].lstrip().startswith(token):
                j += 1
            end = (lines[j][0] + len(lines[j][1])) if j < n else len(text)
            blocks.append(Block(CODE, start, end, text[start:end],
                                line=i + 1))
            i = j + 1
            continue

        if _HRULE.match(stripped):
            flush_para()
            blocks.append(Block(RULE, start, start + len(stripped), bare,
                                line=i + 1))
            i += 1
            continue

        atx = _ATX.match(stripped)
        if atx:
            flush_para()
            blocks.append(Block(HEADING, start, start + len(stripped),
                                atx.group(2), level=len(atx.group(1)),
                                marker=atx.group(1), line=i + 1))
            i += 1
            continue

        # Setext heading: the underline belongs to the paragraph above it,
        # which is why this is checked against the buffered paragraph rather
        # than as a block in its own right.
        if (_SETEXT.match(stripped) and para_lines
                and "".join(para_lines).strip()):
            title = "".join(para_lines).strip()
            level = 1 if stripped.lstrip().startswith("=") else 2
            blocks.append(Block(HEADING, para_start or start,
                                start + len(stripped), title, level=level,
                                marker="=" if level == 1 else "-",
                                line=para_line_no))
            para_start = None
            para_lines = []
            i += 1
            continue

        if _TABLE_ROW.match(stripped):
            flush_para()
            j = i
            while j < n and _TABLE_ROW.match(lines[j][1].rstrip("\r\n")):
                j += 1
            end = lines[j - 1][0] + len(lines[j - 1][1].rstrip("\r\n"))
            blocks.append(Block(TABLE, start, end, text[start:end],
                                line=i + 1))
            i = j
            continue

        if bare.startswith(">"):
            flush_para()
            j = i
            while j < n and lines[j][1].lstrip().startswith(">"):
                j += 1
            end = lines[j - 1][0] + len(lines[j - 1][1].rstrip("\r\n"))
            blocks.append(Block(QUOTE, start, end, text[start:end],
                                line=i + 1))
            i = j
            continue

        num = _NUMBER.match(stripped)
        if num:
            flush_para()
            body_off = start + len(num.group(1)) + len(num.group(2)) + 2
            end, body = _consume_item(lines, i, text,
                                       body_off)
            blocks.append(Block(ORDERED, body_off, end, body,
                                level=len(num.group(1)) // 2,
                                marker=num.group(2) + num.group(3),
                                number=int(num.group(2)), line=i + 1))
            i = _item_lines(lines, i)
            continue

        bul = _BULLET.match(stripped)
        if bul:
            flush_para()
            body_off = start + len(bul.group(1)) + 2
            end, body = _consume_item(lines, i, text,
                                       body_off)
            blocks.append(Block(LIST, body_off, end, body,
                                level=len(bul.group(1)) // 2,
                                marker=bul.group(2), line=i + 1))
            i = _item_lines(lines, i)
            continue

        if para_start is None:
            para_start = start
            para_line_no = i + 1
        para_lines.append(raw)
        para_end = start + len(stripped)
        i += 1

    flush_para()
    blocks.sort(key=lambda b: b.start)
    return blocks


def _item_lines(lines: list[tuple[int, str]], i: int) -> int:
    """Index of the first line after a list item and its continuations."""
    j = i + 1
    n = len(lines)
    while j < n:
        raw = lines[j][1]
        bare = raw.strip()
        if not bare:
            break
        if (_BULLET.match(raw.rstrip("\r\n"))
                or _NUMBER.match(raw.rstrip("\r\n"))
                or _ATX.match(raw.rstrip("\r\n"))
                or _FENCE.match(raw.rstrip("\r\n"))):
            break
        if not raw.startswith((" ", "\t")):
            break
        j += 1
    return j


def _consume_item(lines: list[tuple[int, str]], i: int, text: str,
                  body_off: int) -> tuple[int, str]:
    """End offset of a list item (including its continuation lines) and the
    item's body text, starting after the marker."""
    j = _item_lines(lines, i)
    end = lines[j - 1][0] + len(lines[j - 1][1].rstrip("\r\n"))
    return end, text[body_off:end]


def step_number(text: str) -> int:
    """`Step 4 — tighten the bolt` -> 4, and 0 when there is no step."""
    m = _STEP.match(text or "")
    return int(m.group(1)) if m else 0


# ---------------------------------------------------------------------------
# masking
# ---------------------------------------------------------------------------

_INLINE_CODE = re.compile(r"`+[^`]*`+")
_LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)]*)\)")
_AUTOLINK = re.compile(r"<https?://[^>]*>")
_HTML = re.compile(r"<!--.*?-->", re.S)
_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_EMPH = re.compile(r"(\*{1,3}|_{1,3})")


def _blank(match: re.Match, keep: int = 0) -> str:
    """Same-length replacement, optionally keeping one capture group."""
    text = match.group(0)
    if keep:
        inner = match.group(keep) or ""
        pad = len(text) - len(inner)
        left = (len(match.group(0).split(inner)[0]) if inner in text else 0)
        return " " * left + inner + " " * (pad - left)
    return " " * len(text)


def mask_nonprose(text: str, keep_headings: bool = False) -> str:
    """Replace everything that is not prose with spaces, length-preserving.

    Front matter, fenced code, tables and horizontal rules go. Headings go
    too unless asked for: a heading is a label, not a sentence, and counting
    it as one drags every sentence-length distribution toward six words.
    List markers go, list TEXT stays — an instruction is prose, and it is
    the prose a technical author most needs measured.
    """
    out = list(text)
    for block in scan_blocks(text):
        drop = block.kind in (CODE, TABLE, FRONT, RULE)
        if block.kind == HEADING and not keep_headings:
            drop = True
        if drop:
            for i in range(block.start, min(block.end, len(out))):
                if out[i] != "\n":
                    out[i] = " "
    masked = "".join(out)
    # list markers and blockquote markers, on lines that survived
    masked = re.sub(r"(?m)^(\s*)([-*+]|\d+[.)])(\s)",
                    lambda m: m.group(1) + " " * len(m.group(2)) + m.group(3),
                    masked)
    masked = re.sub(r"(?m)^(\s*)(>+)(\s)",
                    lambda m: m.group(1) + " " * len(m.group(2)) + m.group(3),
                    masked)
    return masked


def mask_inline(text: str) -> str:
    """Blank inline markup, keep the words. Length-preserving."""
    def link(m: re.Match) -> str:
        label = m.group(2)
        head = len(m.group(1)) + 1
        return " " * head + label + " " * (len(m.group(0)) - head -
                                           len(label))
    out = _HTML.sub(lambda m: " " * len(m.group(0)), text)
    out = _INLINE_CODE.sub(lambda m: " " * len(m.group(0)), out)
    out = _LINK.sub(link, out)
    out = _AUTOLINK.sub(lambda m: " " * len(m.group(0)), out)
    out = _TAG.sub(lambda m: " " * len(m.group(0)), out)
    out = _EMPH.sub(lambda m: " " * len(m.group(0)), out)
    return out


def prose_of(text: str, keep_headings: bool = False) -> str:
    """The prose of a markdown file, at the file's own offsets."""
    return mask_inline(mask_nonprose(text, keep_headings))


# ---------------------------------------------------------------------------
# sentences
# ---------------------------------------------------------------------------

# An abbreviation list is a trap, and this is the shape of it. Half of the
# obvious entries -- no, in, min, max, est, art, sec, para, co, ed, pt -- are
# also ordinary English words that end sentences constantly, so a flat list
# makes the splitter SILENTLY UNDER-SPLIT: "It works in principle. No." runs
# on, every length distribution shifts, and nothing announces it. Hence two
# tiers, judged against what FOLLOWS.

#: Never ends a sentence, whatever comes next. Titles and Latin tags.
NEVER_END = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "rev", "hon", "gen",
    "col", "sgt", "lt", "capt", "cmdr", "maj", "pvt", "supt", "insp",
    "vs", "etc", "eg", "ie", "cf", "viz", "al", "et", "ca", "circa",
    "ibid", "op", "cit", "approx", "messrs", "esq", "fr", "sra",
}

#: May end a sentence. Blocks the split only when what follows continues it
#: -- a digit ("see Fig. 7"), a lowercase word, a Roman numeral ("Vol. II")
#: or an initial. Followed by an ordinary capitalised word, it IS a stop.
LABELS = {
    "fig", "figs", "sec", "secs", "no", "nos", "vol", "vols", "ch", "chap",
    "pp", "ed", "eds", "inc", "ltd", "co", "corp", "dept", "univ", "assn",
    "bros", "mt", "ft", "ave", "blvd", "rd", "sq", "pt", "pts", "am", "pm",
    "ad", "bc", "para", "paras", "art", "ref", "refs", "eq", "eqn", "app",
    "appx", "temp", "spec", "specs", "std", "qty", "ea", "hr", "hrs",
    "min", "mins", "max", "avg", "est", "wk", "yr", "yrs", "mo", "mos",
    "km", "cm", "mm", "kg", "lb", "lbs", "oz", "in", "hz", "khz", "mhz",
    "ghz", "nm", "ma", "mv", "kv", "rpm", "psi",
}

#: Kept for hosts that want the whole set; the splitter uses the two tiers.
ABBREVIATIONS = NEVER_END | LABELS

_ROMAN = re.compile(r"[IVXLCDM]+\b")

_TERM = re.compile(r"[.!?…]+[\"'”’)\]]*")
_INITIAL = re.compile(r"(?:^|[\s(\[\"'])[A-Z]$")


def sentences(text: str, base: int = 0) -> list[tuple[int, int]]:
    """Sentence spans (start, end), absolute if `base` is given.

    Trained on the failures that matter in these two document types:
    `Fig. 7`, `§4.2`, `40.5 Nm`, `J. R. R. Tolkien`, `"Go." Then she left.`
    and `e.g. the housing`. A splitter that gets those wrong reports echoes
    and length distributions that are wrong in a way nobody can see.
    """
    spans: list[tuple[int, int]] = []
    n = len(text)
    start = 0
    # A blank line always ends a sentence: it ends a paragraph, and prose
    # that runs a sentence across a paragraph break is not prose we can help.
    hard = {m.start() for m in re.finditer(r"\n[ \t]*\n", text)}

    i = 0
    while i < n:
        if i in hard:
            _emit(spans, text, start, i, base)
            start = i + 1
            i += 1
            continue
        ch = text[i]
        if ch not in ".!?…":
            i += 1
            continue
        m = _TERM.match(text, i)
        end = m.end() if m else i + 1
        if _is_boundary(text, i, end):
            _emit(spans, text, start, end, base)
            start = end
        i = max(end, i + 1)
    _emit(spans, text, start, n, base)
    return spans


def _emit(spans: list[tuple[int, int]], text: str, start: int, end: int,
          base: int) -> None:
    chunk = text[start:end]
    if not chunk.strip():
        return
    lead = len(chunk) - len(chunk.lstrip())
    trail = len(chunk) - len(chunk.rstrip())
    spans.append((base + start + lead, base + end - trail))


def _continues(text: str, end: int) -> bool:
    """After a tier-2 abbreviation, does what follows continue the sentence?"""
    rest = text[end:]
    m = re.match(r"[ \t]*(.)", rest)
    if not m:
        return False
    nxt = m.group(1)
    if nxt.isdigit() or nxt.islower():
        return True
    tok = re.match(r"[ \t]*([A-Za-z]+)", rest)
    if tok and _ROMAN.fullmatch(tok.group(1)):
        return True
    # Deliberately NOT treating a following initial ("Nm. J. R. R. Tolkien")
    # as a continuation. "Sec. A shows" loses, "40 Nm. J. R. R. Tolkien"
    # wins, and the second is far commoner in both document types.
    return False


def _is_boundary(text: str, i: int, end: int) -> bool:
    ch = text[i]
    # a decimal point or a section number: 4.2, 40.5, §4.2.1
    if ch == "." and i + 1 < len(text) and text[i + 1].isdigit():
        if i and text[i - 1].isdigit():
            return False
    if ch == ".":
        j = i - 1
        while j >= 0 and (text[j].isalnum() or text[j] in "'-"):
            j -= 1
        word = text[j + 1:i].lower()
        if word in NEVER_END:
            return False
        if word in LABELS and _continues(text, end):
            return False
        if len(word) == 1 and word.isalpha():
            # "J. R. R. Tolkien" — an initial, not a stop. Judged on the one
            # character before the letter, never on the whole prefix: a
            # prefix search would call every single-letter word an initial
            # the moment the paragraph contained one anywhere.
            if j < 0 or text[j] in " \t\n([\"'\u201c\u2018":
                return False
        # "U.S." / "a.m." — a dotted initialism, not a stop
        if len(word) == 1 and j >= 1 and text[j] == ".":
            return False
    rest = text[end:]
    if not rest.strip():
        return True
    m = re.match(r"[ \t]*(\n?)[ \t]*(.)", rest)
    if not m:
        return True
    if not m.group(1) and not rest[:1].isspace():
        # "4.2mm" or "e.g.something" — no space, not a boundary
        return False
    nxt = m.group(2)
    if nxt.isupper() or nxt.isdigit():
        return True
    return nxt in "\"'“‘([#*->—"


# ---------------------------------------------------------------------------
# words and syllables
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[A-Za-zÀ-ɏ][A-Za-zÀ-ɏ'’\-]*")


def words(text: str, base: int = 0) -> list[tuple[int, int, str]]:
    """Word spans and their text. Hyphenated words count once."""
    return [(base + m.start(), base + m.end(), m.group(0))
            for m in _WORD_RE.finditer(text)]


def word_list(text: str) -> list[str]:
    return [m.group(0) for m in _WORD_RE.finditer(text)]


def normalise(word: str) -> str:
    """Lowercase, strip accents and curly apostrophes. For counting only."""
    out = unicodedata.normalize("NFKD", word.replace("’", "'"))
    out = "".join(c for c in out if not unicodedata.combining(c))
    return out.lower()


def term_key(term: str) -> str:
    """The key two surface forms of one term must share.

    `Wi-Fi`, `WiFi`, `wi fi` and `wifi` collapse; `power supply` and `power
    supplies` collapse; `power supply unit` does not collapse into either,
    because it is a different term and merging it would be the tool
    inventing a defect.
    """
    base = normalise(term)
    base = re.sub(r"[^a-z0-9]+", "", base)
    for suffix, repl in (("ies", "y"), ("ses", "s"), ("es", ""), ("s", "")):
        if len(base) > 4 and base.endswith(suffix):
            return base[: len(base) - len(suffix)] + repl
    return base


_VOWELS = "aeiouy"


def syllables(word: str) -> int:
    """A syllable estimate. Every readability score rests on this one
    heuristic, which is why the scores are reported as proxies."""
    w = normalise(word).strip("'-")
    w = re.sub(r"[^a-z]", "", w)
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    count = 0
    prev_vowel = False
    for ch in w:
        is_v = ch in _VOWELS
        if is_v and not prev_vowel:
            count += 1
        prev_vowel = is_v
    # Silent trailing e, then the consonant+le exception put back. Order
    # matters: "simple" is two vowel groups, minus the silent e, plus the
    # -ple = 2. Skipping the subtraction for -le (the obvious shortcut)
    # gives 3 and every readability score drifts with it.
    if w.endswith("e") and not w.endswith(("ee", "ye")):
        count -= 1
    if w.endswith("le") and len(w) > 2 and w[-3] not in _VOWELS:
        count += 1
    if w.endswith(("ed",)) and len(w) > 3 and w[-3] not in "td":
        count -= 1
    return max(1, count)


# ---------------------------------------------------------------------------
# word lists
#
# A proxy, and said to be one. Rarity here means "outside a list of common
# English words", not "rare in English" — no corpus ships with this package
# and inventing one from the manuscript itself would measure the manuscript
# against itself, which is a tautology dressed as a finding.
# ---------------------------------------------------------------------------

STOPWORDS = set("""
a about above after again against all am an and any are as at be because
been before being below between both but by can cannot could did do does
doing down during each few for from further had has have having he her here
hers herself him himself his how i if in into is it its itself just me more
most my myself no nor not now of off on once only or other our ours
ourselves out over own same she should so some such than that the their
theirs them themselves then there these they this those through to too
under until up very was we were what when where which while who whom why
will with would you your yours yourself yourselves
""".split())

COMMON = STOPWORDS | set("""
able across act add afraid age ago agree air allow almost alone along
already also although always among amount animal another answer appear area
arm around arrive art ask away baby back bad bag ball bank base beautiful
become bed begin behind believe below best better big bill bird bit black
blood blue board boat body book born both box boy break bring brother build
business busy buy call car care carry case catch cause cell centre certain
chance change character charge check child choose church city claim class
clean clear close coffee cold college colour come common community company
compare complete computer condition consider contain continue control cook
copy corner cost country couple course cover create cross cup cut dark data
daughter day dead deal death decide deep degree describe design detail
develop die difference different difficult dinner direct discover discuss
distance doctor dog door doubt draw dream dress drink drive drop dry early
earth easy eat edge education effect effort eight either else end enough
enter entire environment especially even evening event ever every example
except exist expect experience explain eye face fact fail fall family far
fast father fear feel few field fight figure fill film final find fine
finger finish fire first fish fit five floor flow fly follow food foot
force forget form forward four free friend front full fun future game
garden general get girl give glass go god gold good government great green
ground group grow guess gun guy hair half hand hang happen happy hard head
health hear heart heat heavy help hide high history hit hold home hope
horse hospital hot hotel hour house however human hundred husband idea
identify image imagine important improve include increase indeed industry
information inside instead interest involve issue itself job join keep key
kid kill kind kitchen knife know land language large last late laugh law
lay lead learn leave left leg length less let letter level lie life light
like line list listen little live local long look lose lot love low machine
main maintain major make man manage many market marry material matter may
maybe mean measure meet member memory mention message method middle might
mile military million mind minute miss model modern moment money month
moon morning mother mountain mouth move much music must name nation natural
nature near necessary need never new news next nice night nine none normal
north nothing notice number object occur ocean offer office officer often
oil old open operation opportunity option order organisation organization
original others outside page pain paper parent part particular party pass
past pay peace people perform perhaps period person phone physical pick
picture piece place plan plant play please point police policy political
poor popular position possible power practice prepare present president
press pretty prevent price probably problem process produce product
professional program project property protect prove provide public pull
purpose push put quality question quick quiet quite race radio raise range
rate rather reach read ready real reason receive recent recognise record
red reduce reflect region relationship remain remember remove report
represent require research respond response responsibility rest result
return rich right rise risk road rock role room rule run safe save say
scene school science score sea season seat second section security see seek
seem sell send sense series serious serve service set seven several sex
shake share sharp shoot short should shoulder show side sign significant
similar simple since sing single sister sit site situation six size skill
skin sky sleep slow small smile snow social society soft soldier solution
some son song soon sort sound source south space speak special specific
speed spend sport spring staff stage stand standard star start state
station stay step stick still stock stone stop store story straight
strategy street strong structure student study stuff style subject success
suddenly suffer suggest summer sun support sure surface system table take
talk task teach teacher team technology television tell ten term test text
thank theory thing think third though thought thousand threat three throw
thus time today together tonight top total touch toward town trade
tradition traffic train travel treat tree trial trip trouble true trust
truth try turn twenty two type understand unit until upon use usually value
various very view village visit voice wait walk wall want war watch water
way weapon wear week weight welcome well west wet what whatever wheel when
whether white whole wide wife wild win wind window wine winter wish within
without woman wonder wood word work world worry worth write wrong yard year
yes yesterday yet young
""".split())


def is_common(word: str) -> bool:
    return normalise(word).strip("'-") in COMMON
