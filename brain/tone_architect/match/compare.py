"""Distance between two fingerprints, broken down so the result explains itself.

Each part is scaled so that 1.0 means "clearly audible difference" for that feature (roughly a
3 dB EQ difference, a 10% delay-time error, and so on); the total is a weighted sum.
"""

from __future__ import annotations

import math

from .fingerprint import BAND_CENTERS_HZ, Fingerprint

# (weight, scale): part = |difference| / scale, total = sum(weight * part)
SPECTRUM = (3.0, 3.0)  # RMS dB difference across the 1/3-octave bands
TILT = (1.0, 1.0)  # dB per octave
CREST = (1.5, 2.0)  # dB
FLATNESS = (1.5, 5.0)  # dB
DYNAMICS = (1.0, 4.0)  # dB
DELAY_TIME = (2.0, 0.1)  # |log2 ratio|; 0.1 is ~7%
DELAY_MISSING = 2.0  # one has a clear delay, the other doesn't
DECAY = (0.5, 20.0)  # dB/s
MOD_MISSING = 0.5  # low weight: modulation detection is the roughest feature


def distance(ref: Fingerprint, cand: Fingerprint) -> tuple[float, dict[str, float]]:
    parts: dict[str, float] = {}

    diffs = [a - b for a, b in zip(ref.band_db, cand.band_db, strict=True)]
    parts["spectrum"] = math.sqrt(sum(d * d for d in diffs) / len(diffs)) / SPECTRUM[1]
    parts["tilt"] = abs(ref.tilt_db_per_oct - cand.tilt_db_per_oct) / TILT[1]
    parts["crest"] = abs(ref.crest_db - cand.crest_db) / CREST[1]
    parts["flatness"] = abs(ref.flatness_db - cand.flatness_db) / FLATNESS[1]
    parts["dynamics"] = abs(ref.dynamic_range_db - cand.dynamic_range_db) / DYNAMICS[1]

    if ref.delay_ms and cand.delay_ms:
        parts["delay"] = abs(math.log2(ref.delay_ms / cand.delay_ms)) / DELAY_TIME[1]
    elif bool(ref.delay_ms) != bool(cand.delay_ms):
        parts["delay"] = DELAY_MISSING
    else:
        parts["delay"] = 0.0

    if ref.decay_db_per_s is not None and cand.decay_db_per_s is not None:
        parts["decay"] = min(3.0, abs(ref.decay_db_per_s - cand.decay_db_per_s) / DECAY[1])
    else:
        parts["decay"] = 0.0

    parts["modulation"] = 1.0 if bool(ref.mod_rate_hz) != bool(cand.mod_rate_hz) else 0.0

    weights = {
        "spectrum": SPECTRUM[0],
        "tilt": TILT[0],
        "crest": CREST[0],
        "flatness": FLATNESS[0],
        "dynamics": DYNAMICS[0],
        "delay": DELAY_TIME[0],
        "decay": DECAY[0],
        "modulation": MOD_MISSING,
    }
    total = sum(weights[k] * v for k, v in parts.items())
    return round(total, 3), {k: round(v, 3) for k, v in parts.items()}


def explain(ref: Fingerprint, cand: Fingerprint) -> list[str]:
    """Plain-language notes on what's off, biggest first. Fed to the brain when it revises."""
    notes: list[tuple[float, str]] = []
    _, parts = distance(ref, cand)

    if parts["spectrum"] > 0.5 or parts["tilt"] > 0.5:
        worst = max(range(len(ref.band_db)), key=lambda i: abs(ref.band_db[i] - cand.band_db[i]))
        diff = cand.band_db[worst] - ref.band_db[worst]
        word = "too much" if diff > 0 else "not enough"
        notes.append(
            (
                parts["spectrum"],
                f"{word} energy around {BAND_CENTERS_HZ[worst]:.0f} Hz "
                f"({diff:+.1f} dB vs reference); overall tilt {cand.tilt_db_per_oct:+.2f} vs "
                f"{ref.tilt_db_per_oct:+.2f} dB/oct",
            )
        )
    if parts["crest"] > 0.5 or parts["flatness"] > 0.5:
        more = cand.flatness_db < ref.flatness_db or cand.crest_db > ref.crest_db
        notes.append(
            (
                max(parts["crest"], parts["flatness"]),
                f"{'less' if more else 'more'} distorted than the reference (crest "
                f"{cand.crest_db} vs {ref.crest_db} dB, flatness {cand.flatness_db} vs "
                f"{ref.flatness_db} dB)",
            )
        )
    if parts["dynamics"] > 0.5:
        word = "less" if cand.dynamic_range_db > ref.dynamic_range_db else "more"
        notes.append(
            (
                parts["dynamics"],
                f"{word} compressed than the reference (dynamic range "
                f"{cand.dynamic_range_db} vs {ref.dynamic_range_db} dB)",
            )
        )
    if parts["delay"] > 0.5:
        if ref.delay_ms and cand.delay_ms:
            text = f"delay repeats at {cand.delay_ms:.0f} ms, reference at {ref.delay_ms:.0f} ms"
        elif ref.delay_ms:
            text = f"reference has a delay at {ref.delay_ms:.0f} ms; candidate has none audible"
        else:
            text = f"candidate has an audible delay at {cand.delay_ms:.0f} ms; reference doesn't"
        notes.append((parts["delay"], text))
    if parts["decay"] > 0.5:
        word = "longer" if (cand.decay_db_per_s or 0) > (ref.decay_db_per_s or 0) else "shorter"
        notes.append((parts["decay"], f"tails ring {word} than the reference"))
    if parts["modulation"]:
        if ref.mod_rate_hz:
            notes.append((0.5, f"reference has modulation around {ref.mod_rate_hz} Hz"))
        else:
            notes.append((0.5, "candidate has modulation the reference doesn't"))

    return [text for _, text in sorted(notes, key=lambda n: -n[0])]
