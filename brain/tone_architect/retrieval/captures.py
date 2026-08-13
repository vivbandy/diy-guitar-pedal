"""Keyword/tag/gain scoring over the capture library.

Deliberately dumb and deterministic — the LLM does the tone reasoning, retrieval only has to put
plausible candidates in front of it. The one hard requirement is coverage: the candidate list must
always contain at least one amp and at least one cab, or the model cannot satisfy the cabinet rule.
"""

from __future__ import annotations

import re

from ..models import Capture, CaptureCategory, CaptureGain

_GAIN_WORDS: dict[CaptureGain, tuple[str, ...]] = {
    CaptureGain.clean: ("clean", "sparkle", "sparkly", "glassy", "jangle", "pristine", "chime"),
    CaptureGain.crunch: ("crunch", "breakup", "edge of breakup", "bluesy", "gritty", "raw"),
    CaptureGain.mid_gain: ("drive", "overdrive", "lead", "rock", "sustain", "singing", "solo"),
    CaptureGain.high_gain: ("metal", "djent", "high gain", "brutal", "chug", "thrash", "heavy"),
    CaptureGain.fuzz: ("fuzz", "muff", "wooly", "woolly", "gated fuzz", "velcro"),
}

_STOPWORDS = frozenset(
    """a an and the of for with in on to my me i like sound sounds tone tones get make
    please something kinda kind sort very really that this it his her their""".split()
)


def tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if t and t not in _STOPWORDS}


def score_capture(capture: Capture, request: str, tokens: set[str] | None = None) -> float:
    tokens = tokens if tokens is not None else tokenize(request)
    lowered = request.lower()
    score = 0.0

    for tag in capture.tags:
        if tag.lower() in lowered:
            score += 3.0
        elif tokens & tokenize(tag):
            score += 1.5

    for trait in capture.character:
        if trait.lower() in lowered:
            score += 2.0
        elif tokens & tokenize(trait):
            score += 1.0

    name_hits = tokens & tokenize(capture.name)
    score += 1.5 * len(name_hits)

    for gain, words in _GAIN_WORDS.items():
        if capture.gain is gain and any(w in lowered for w in words):
            score += 2.5

    return score


def score_captures(captures: list[Capture], request: str, limit: int = 24) -> list[Capture]:
    """Rank captures, then guarantee amp + cab coverage regardless of the ranking."""
    tokens = tokenize(request)
    ranked = sorted(
        captures,
        key=lambda c: (-score_capture(c, request, tokens), c.id),
    )
    selected = ranked[:limit]

    for category in (CaptureCategory.amp, CaptureCategory.cab):
        if any(c.category is category for c in selected):
            continue
        fallback = next((c for c in ranked if c.category is category), None)
        if fallback is not None:
            selected.append(fallback)

    # An amp-head-only candidate list makes the cabinet rule unsatisfiable, so make sure a
    # full-rig option is offered too when the library has one.
    amps = [c for c in selected if c.category is CaptureCategory.amp]
    if amps and not any(c.includes_cab for c in amps):
        full_rig = next(
            (c for c in ranked if c.category is CaptureCategory.amp and c.includes_cab), None
        )
        if full_rig is not None:
            selected.append(full_rig)

    seen: set[str] = set()
    out: list[Capture] = []
    for c in selected:
        if c.id not in seen:
            seen.add(c.id)
            out.append(c)
    return out


def format_candidates(captures: list[Capture]) -> str:
    lines = []
    for c in captures:
        bits = [
            f"id={c.id}",
            f"name={c.name!r}",
            f"category={c.category.value}",
            f"format={c.format.value}",
            f"gain={c.gain.value}",
            f"includes_cab={str(c.includes_cab).lower()}",
        ]
        if c.character:
            bits.append("character=" + "/".join(c.character))
        if c.tags:
            bits.append("tags=" + "/".join(c.tags))
        lines.append("- " + "  ".join(bits))
    return "\n".join(lines)
