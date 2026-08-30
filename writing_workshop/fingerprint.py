# SPDX-License-Identifier: Apache-2.0
"""The style fingerprint — the addition worth arguing hardest for.

Every AI writing tool has the same unadmitted defect: **use it long enough
and the prose converges on the model's voice.** Not through any single bad
suggestion — each one looks like an improvement — but cumulatively, because
the model has a house style and every accepted edit moves one sentence
toward it. The author ends up with a manuscript that reads competent and
anonymous and cannot point at where it happened.

This matters MORE for a technical manual than for a novel, not less: an
organisation's documentation has a voice, a register and conventions that
exist for reasons, and a model flattens all three while appearing to help.

The defence is arithmetic. Fit a measurable fingerprint on writing the
author has already done and accepted, score every suggestion against it
BEFORE it is offered, and show the drift in specifics:

    *This rewrite is cleaner. It is also 40% shorter per sentence than
    your baseline, drops two of the three subordinate clauses, and
    replaces one word you use often with one you have never used. Accept
    it as a simplification, not as your voice.*

**The measurement decision that makes this work: metrics are fitted PER
WINDOW, not over the whole document.** A 120,000-word baseline and a
sixty-word suggestion are not comparable quantities — the long text's
averages are far more stable, so a naive z-score calls every suggestion an
outlier. Fitting on windows of a few sentences each gives a spread at the
size a suggestion actually is, and the score means something.

The fingerprint is also the honest answer to *"can it write like me?"*: it
cannot, and it should say so — but it can tell you when it is not.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import statistics as stats

from . import textio as T
from .types import Drift, Fingerprint

#: Sentences per fitting window. Small enough that a suggestion is one
#: window, large enough that a single short sentence does not dominate.
WINDOW_SENTENCES = 6

SUBORDINATORS = {
    "although", "though", "because", "since", "while", "whereas", "unless",
    "until", "when", "whenever", "after", "before", "if", "whether",
    "which", "who", "whom", "whose", "where", "that", "as", "so",
}
ARTICLES = {"a", "an", "the"}

#: Metrics that are COUNTS expressed per 1000 words. On a sixty-word
#: suggestion one semicolon is 16.7 per 1000, so a single occurrence can
#: look like a wild departure from a baseline of zero. Below two
#: occurrences' worth of difference there is no evidence of a voice, only
#: of a coin flip, and the fingerprint says nothing rather than shouting.
COUNT_RATES = {"semicolons", "dashes", "adverbs", "similes"}
NOISE_OCCURRENCES = 2.0
_SIMILE = re.compile(r"\b(?:like a|like an|as if|as though|as \w+ as)\b",
                     re.I)
#: `\w{4,}ly` needed SIX letters, not four: the quantifier runs
#: BEFORE the literal "ly", so "badly", "sadly", "aptly" and
#: "wryly" were never adverbs as far as this package was concerned.
#: Two letters plus "ly" is the rule that was meant.
_LY = re.compile(r"\b[a-z]{2,}ly\b", re.I)
_LY_KEEP = {"only", "early", "family", "reply", "supply", "apply", "likely",
            "lonely", "holy", "ugly", "silly", "daily", "weekly", "monthly",
            "yearly", "friendly", "lovely", "assembly"}
_QUOTED = re.compile(r"[\"“]([^\"“”]{2,600}?)[\"”]", re.S)

#: (key, human label, "higher means…") — the label is what the author
#: reads, so it says what the number MEANS rather than what it is.
METRICS: tuple[tuple[str, str, str, str], ...] = (
    ("sentence_words", "sentence length", "longer", "shorter"),
    ("sentence_spread", "variety in sentence length", "more varied",
     "flatter"),
    ("comma_density", "commas per 100 words", "more punctuated", "plainer"),
    ("semicolons", "semicolons per 1000 words", "more", "fewer"),
    ("dashes", "dashes per 1000 words", "more", "fewer"),
    ("subordination", "subordinate clauses per sentence", "more layered",
     "flatter"),
    ("rarity", "share of uncommon words", "rarer vocabulary",
     "plainer vocabulary"),
    ("ttr", "vocabulary variety", "more varied", "more repetitive"),
    ("adverbs", "-ly adverbs per 1000 words", "more", "fewer"),
    ("article_openings", "sentences opening with a/an/the", "more", "fewer"),
    ("similes", "similes per 1000 words", "more", "fewer"),
    ("dialogue", "share of words in dialogue", "more dialogue",
     "less dialogue"),
)
LABELS = {key: label for key, label, _u, _d in METRICS}


def measure(text: str) -> dict[str, float]:
    """Every metric for one piece of text. Pure arithmetic."""
    spans = T.sentences(text)
    words = T.word_list(text)
    n_words = len(words)
    if not spans or n_words < 5:
        return {}
    lengths = [len(T.word_list(text[s:e])) for s, e in spans]
    lengths = [n for n in lengths if n]
    if not lengths:
        return {}
    lowered = [T.normalise(w).strip("'-") for w in words]
    per_1000 = 1000.0 / n_words

    subordinate = sum(1 for w in lowered if w in SUBORDINATORS)
    opens = 0
    for s, e in spans:
        toks = T.word_list(text[s:e])
        if toks and T.normalise(toks[0]) in ARTICLES:
            opens += 1
    quoted = sum(len(T.word_list(m.group(1))) for m in _QUOTED.finditer(text))

    return {
        "sentence_words": stats.fmean(lengths),
        "sentence_spread": (stats.pstdev(lengths) / stats.fmean(lengths)
                            if len(lengths) > 1 and stats.fmean(lengths)
                            else 0.0),
        "comma_density": 100.0 * text.count(",") / n_words,
        "semicolons": text.count(";") * per_1000,
        "dashes": (text.count("—") + text.count(" - ")
                   + text.count("–")) * per_1000,
        "subordination": subordinate / len(lengths),
        "rarity": sum(1 for w in lowered if not T.is_common(w)) / n_words,
        "ttr": mattr(lowered),
        "adverbs": sum(1 for w in lowered
                       if _LY.fullmatch(w) and w not in _LY_KEEP) * per_1000,
        "article_openings": opens / len(spans),
        "similes": len(_SIMILE.findall(text)) * per_1000,
        "dialogue": quoted / n_words,
        # Carried so `score` can tell a voice from a coin flip. Not a
        # metric: it never appears in METRICS and is never fitted.
        "_words": float(n_words),
    }


def mattr(tokens: list[str], window: int = 50) -> float:
    """Moving-average type-token ratio.

    Plain TTR is a length measurement wearing a vocabulary costume — every
    text gets a lower score the longer it is, so a chapter always looks
    "more repetitive" than a paragraph. A fixed window removes the length
    dependence, which is the whole reason a baseline and a suggestion can
    be compared at all.
    """
    if not tokens:
        return 0.0
    if len(tokens) <= window:
        return len(set(tokens)) / len(tokens)
    ratios = []
    for i in range(0, len(tokens) - window + 1, max(1, window // 2)):
        chunk = tokens[i:i + window]
        ratios.append(len(set(chunk)) / len(chunk))
    return stats.fmean(ratios) if ratios else 0.0


def windows(text: str, sentences: int = WINDOW_SENTENCES) -> list[str]:
    """Fitting windows over one text.

    The final short group is dropped -- a two-sentence tail is not a
    sample of anything. But a text SHORTER than one window still yields
    one window rather than none: silently returning an empty fingerprint
    for a short piece meant `score()` returned [], `drift_score()` returned
    0.0, and the panel showed "sounds like you" for a suggestion it had
    never measured. A baseline that is thin says it is thin; one that
    quietly says nothing is the failure mode this whole module exists to
    prevent.
    """
    spans = T.sentences(text)
    if not spans:
        return []
    out = []
    for i in range(0, len(spans), sentences):
        group = spans[i:i + sentences]
        if len(group) < max(2, sentences // 2):
            continue
        out.append(text[group[0][0]:group[-1][1]])
    if not out and len(T.word_list(text)) >= 20:
        out.append(text[spans[0][0]:spans[-1][1]])
    return out


def fit(texts: list[str], *, fitted_on: str = "",
        sentences: int = WINDOW_SENTENCES) -> Fingerprint:
    """Fit on writing the author has already done and ACCEPTED.

    "Accepted" is load-bearing. Fitting on a draft that already contains
    the model's rewrites bakes the drift into the baseline, and the tool
    then reports that everything matches beautifully — the exact failure
    it exists to prevent.
    """
    rows: list[dict[str, float]] = []
    n_words = 0
    n_sent = 0
    for text in texts:
        n_words += len(T.word_list(text))
        n_sent += len(T.sentences(text))
        for window in windows(text, sentences):
            row = measure(window)
            if row:
                rows.append(row)
    fp = Fingerprint(n_words=n_words, n_sentences=n_sent,
                     fitted_on=fitted_on)
    if not rows:
        return fp
    for key, _label, _u, _d in METRICS:
        values = [row[key] for row in rows if key in row]
        if not values:
            continue
        fp.metrics[key] = round(stats.fmean(values), 5)
        fp.spread[key] = round(stats.pstdev(values), 5) if len(values) > 1 \
            else 0.0
    fp.metrics["_windows"] = len(rows)
    return fp


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def score(fp: Fingerprint, text: str) -> list[Drift]:
    """How far one piece of text sits from the author's own baseline."""
    row = measure(text)
    if not row or not fp.metrics:
        return []
    out: list[Drift] = []
    for key, label, up, down in METRICS:
        if key not in row or key not in fp.metrics:
            continue
        base = fp.metrics[key]
        sd = fp.spread.get(key, 0.0)
        value = row[key]
        # TWO WAYS TO GET A MEANINGLESS NUMBER HERE, and both produced one.
        #
        # A baseline with NO spread on a metric cannot say how unusual a
        # value is -- only whether it differs. Reporting a flat +/-3 for
        # any difference at all made a passage score 3.0 against a
        # baseline fitted on ITSELF. So a flat metric is scored on the
        # relative difference and capped at 3: a 10% difference reads as
        # 0.3, a doubling as 3.
        #
        # And a baseline with a NEARLY flat spread is worse than a flat
        # one: dividing by 0.0001 produced z = 55.6, which then swamped
        # the root-mean-square and made every other measure invisible.
        # Anything under 2% of the baseline counts as flat, and every real
        # z is clamped to +/-6 -- past that the number has stopped meaning
        # anything and is only distorting the summary.
        if key in COUNT_RATES:
            words = row.get("_words", 0.0)
            noise = NOISE_OCCURRENCES * 1000.0 / max(words, 1.0)
            if abs(value - base) < noise:
                out.append(Drift(metric=key, label=label,
                                 baseline=round(base, 4),
                                 value=round(value, 4), z=0.0,
                                 direction="within counting noise"))
                continue
        flat = sd <= max(1e-9, abs(base) * 0.02)
        if flat:
            scale = max(abs(base), 1e-6)
            z = _clamp(3.0 * (value - base) / scale, 3.0)
        else:
            z = _clamp((value - base) / sd, 6.0)
        out.append(Drift(metric=key, label=label, baseline=round(base, 4),
                         value=round(value, 4), z=round(z, 2),
                         direction=up if value > base else down))
    out.sort(key=lambda d: -abs(d.z))
    return out


def drift_score(drifts: list[Drift]) -> float:
    """One number to put beside a suggestion. Quiet, per decision 4.

    Root-mean-square of the notable z-scores. 0 is "sounds like you";
    above about 1.5 is "this does not".
    """
    notable = [d.z for d in drifts if d.notable] or [d.z for d in drifts]
    if not notable:
        return 0.0
    return round((sum(z * z for z in notable) / len(notable)) ** 0.5, 2)


def describe(fp: Fingerprint, drifts: list[Drift], limit: int = 3) -> str:
    """The sentence the author reads. Specific, or it says nothing."""
    if not drifts:
        return ""
    if not fp.trustworthy:
        head = (f"Baseline fitted on only {fp.n_words:,} words, so treat "
                f"this as indicative: ")
    else:
        head = ""
    notable = [d for d in drifts if d.notable][:limit]
    if not notable:
        return head + "This sits inside your usual range on every measure."
    parts = []
    for drift in notable:
        if drift.baseline:
            pct = abs(drift.value - drift.baseline) / abs(drift.baseline)
            parts.append(f"{pct:.0%} {drift.direction} on "
                         f"{drift.label}")
        else:
            parts.append(f"{drift.direction} on {drift.label}")
    return (head + "Against your own writing this is "
            + ", ".join(parts[:-1])
            + (" and " if len(parts) > 1 else "") + parts[-1]
            + ". Accept it as a change, not as your voice.")


# ---------------------------------------------------------------------------
# fitting from a manuscript, and persistence
# ---------------------------------------------------------------------------


def from_manuscript(doc, *, sections=None, fitted_on: str = "") -> Fingerprint:
    texts = []
    for sec in (sections if sections is not None else doc.sections):
        body = doc.prose(sec).strip()
        if body:
            texts.append(body)
    return fit(texts, fitted_on=fitted_on or f"{len(texts)} sections")


def save(fp: Fingerprint, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "metrics": fp.metrics, "spread": fp.spread, "n_words": fp.n_words,
        "n_sentences": fp.n_sentences, "fitted_on": fp.fitted_on,
        "version": fp.version}, indent=2), encoding="utf-8")
    return path


def load(path: str | Path) -> Fingerprint | None:
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return Fingerprint(metrics=data.get("metrics") or {},
                       spread=data.get("spread") or {},
                       n_words=int(data.get("n_words") or 0),
                       n_sentences=int(data.get("n_sentences") or 0),
                       fitted_on=data.get("fitted_on", ""),
                       version=int(data.get("version") or 1))
