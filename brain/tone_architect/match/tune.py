"""Tune a patch's continuous knobs so its render matches a reference recording.

    reference.wav ─ fingerprint ─┐
                                 ├─ distance ─ coordinate search over knobs ─ tuned patch.json
    di.wav + patch ─ tone_render ─ fingerprint ─┘

The brain picks the *structure* (which captures, which effects, in what order). This tunes the
numbers it can't hear: how hard each capture is driven, EQ band gains, compressor, delay time /
feedback / mix, reverb, modulation. Captures themselves are frozen; choosing different ones is
the brain's job between tuning runs.

Things the reference measures directly are seeded instead of searched: a detected delay time
becomes the delay's time_ms (adding a delay node if the patch has none), and a detected
modulation rate becomes the modulation's rate_hz.
"""

from __future__ import annotations

import copy
import json
import math
import os
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .compare import distance
from .fingerprint import Fingerprint, fingerprint_file

# A neutral "match EQ" added after the cab when the patch has no EQ to tune.
MATCH_EQ_BANDS = [
    {"freq_hz": 120, "gain_db": 0, "q": 0.7, "shape": "low_shelf"},
    {"freq_hz": 500, "gain_db": 0, "q": 0.9, "shape": "bell"},
    {"freq_hz": 1500, "gain_db": 0, "q": 0.9, "shape": "bell"},
    {"freq_hz": 3500, "gain_db": 0, "q": 0.9, "shape": "bell"},
    {"freq_hz": 6000, "gain_db": 0, "q": 0.7, "shape": "high_shelf"},
]


@dataclass
class Knob:
    node: int
    key: str  # param name, or "bands.<i>.gain_db"
    lo: float
    hi: float
    step: float
    log: bool = False  # step multiplicatively (times, decays)

    @property
    def name(self) -> str:
        return f"{self.node}:{self.key}"

    def get(self, patch: dict) -> float:
        params = patch["chain"][self.node]["params"]
        if self.key.startswith("bands."):
            _, i, k = self.key.split(".")
            return float(params["bands"][int(i)][k])
        return float(params[self.key])

    def set(self, patch: dict, value: float) -> None:
        value = round(min(self.hi, max(self.lo, value)), 3)
        params = patch["chain"][self.node]["params"]
        if self.key.startswith("bands."):
            _, i, k = self.key.split(".")
            params["bands"][int(i)][k] = value
        else:
            params[self.key] = value

    def moved(self, value: float, direction: int, step: float) -> float:
        return value * (1 + step) ** direction if self.log else value + direction * step


@dataclass
class TuneResult:
    patch: dict
    score: float
    parts: dict[str, float]
    start_score: float
    evaluations: int
    history: list[dict] = field(default_factory=list)


def default_renderer() -> Path:
    override = os.getenv("TONE_RENDER")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "plugin" / "render" / ".build" / "tone_render"


def make_render_fn(
    manifest: Path, di: Path, renderer: Path | None = None
) -> Callable[[dict], Path]:
    renderer = renderer or default_renderer()
    if not renderer.is_file():
        raise FileNotFoundError(
            f"renderer not found at {renderer}; build it with plugin/render/build.sh "
            "(or set TONE_RENDER)"
        )
    workdir = Path(tempfile.mkdtemp(prefix="tone-match-"))
    counter = iter(range(1_000_000))

    def render(patch: dict) -> Path:
        n = next(counter)
        patch_path = workdir / f"cand{n}.json"
        out_path = workdir / f"cand{n}.wav"
        patch_path.write_text(json.dumps(patch))
        proc = subprocess.run(
            [
                str(renderer),
                "--patch",
                str(patch_path),
                "--manifest",
                str(manifest),
                "--in",
                str(di),
                "--out",
                str(out_path),
                "--tail",
                "1",
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"tone_render failed: {proc.stderr.strip()}")
        patch_path.unlink(missing_ok=True)
        return out_path

    return render


def prepare(patch: dict, ref: Fingerprint) -> dict:
    """Seed what the reference measures directly, and make sure there's an EQ to tune."""
    patch = copy.deepcopy(patch)
    chain = patch["chain"]
    types = [n["type"] for n in chain]

    if "eq" not in [n["type"] for n in chain if n.get("enabled", True)]:
        after = max((i for i, t in enumerate(types) if t in ("ir_cab", "nam_capture")), default=-1)
        chain.insert(
            after + 1,
            {
                "type": "eq",
                "enabled": True,
                "label": "Match EQ",
                "params": {"bands": copy.deepcopy(MATCH_EQ_BANDS)},
            },
        )
        types = [n["type"] for n in chain]

    if ref.delay_ms:
        delays = [n for n in chain if n["type"] == "delay"]
        if delays:
            delays[0]["enabled"] = True
            delays[0]["params"]["time_ms"] = round(ref.delay_ms, 1)
        else:
            at = types.index("reverb") if "reverb" in types else len(chain)
            chain.insert(
                at,
                {
                    "type": "delay",
                    "enabled": True,
                    "label": "Matched delay",
                    "params": {
                        "time_ms": round(ref.delay_ms, 1),
                        "feedback": 0.3,
                        "mix": 0.25,
                        "style": "analog",
                    },
                },
            )

    if ref.mod_rate_hz:
        for node in chain:
            if node["type"] == "modulation":
                node["params"]["rate_hz"] = ref.mod_rate_hz
    return patch


def knobs_for(patch: dict, ref: Fingerprint) -> list[Knob]:
    knobs: list[Knob] = []
    for i, node in enumerate(patch["chain"]):
        if not node.get("enabled", True):
            continue
        p = node.get("params", {})
        t = node["type"]
        if t == "nam_capture":
            p.setdefault("input_level_db", 0)
            knobs.append(Knob(i, "input_level_db", -12, 12, 3))
        elif t == "drive":
            knobs += [Knob(i, "drive", 0, 1, 0.15), Knob(i, "tone", 0, 1, 0.15)]
        elif t == "compressor":
            p.setdefault("threshold_db", -18)
            p.setdefault("ratio", 4)
            knobs += [Knob(i, "threshold_db", -40, 0, 6), Knob(i, "ratio", 1, 12, 2)]
        elif t == "eq":
            for b in range(len(p.get("bands", []))):
                knobs.append(Knob(i, f"bands.{b}.gain_db", -12, 12, 3))
        elif t == "delay":
            p.setdefault("time_ms", 400)
            p.setdefault("feedback", 0.3)
            p.setdefault("mix", 0.25)
            if not ref.delay_ms:  # measured times are seeded, not searched
                knobs.append(Knob(i, "time_ms", 50, 1500, 0.1, log=True))
            knobs += [Knob(i, "feedback", 0, 0.8, 0.1), Knob(i, "mix", 0, 0.6, 0.08)]
        elif t == "reverb":
            p.setdefault("mix", 0.2)
            p.setdefault("decay_s", 2.0)
            knobs += [Knob(i, "mix", 0, 0.6, 0.08), Knob(i, "decay_s", 0.3, 8, 0.4, log=True)]
        elif t == "modulation":
            p.setdefault("depth", 0.5)
            p.setdefault("mix", 0.5)
            knobs += [Knob(i, "depth", 0, 1, 0.15), Knob(i, "mix", 0, 1, 0.15)]
    return knobs


def tune(
    patch: dict,
    ref: Fingerprint,
    render: Callable[[dict], Path],
    max_evals: int = 80,
    log: Callable[[str], None] = lambda _: None,
) -> TuneResult:
    """Coordinate search: nudge each knob up/down, keep what helps, shrink steps when stuck."""
    current = prepare(patch, ref)
    knobs = knobs_for(current, ref)
    steps = {k.name: k.step for k in knobs}
    evals = 0
    history: list[dict] = []

    def score(candidate: dict) -> tuple[float, dict[str, float]]:
        nonlocal evals
        evals += 1
        wav = render(candidate)
        try:
            return distance(ref, fingerprint_file(wav))
        finally:
            wav.unlink(missing_ok=True)

    best, parts = score(current)
    start = best
    log(f"start: {best:.2f} {parts}")
    history.append({"eval": evals, "score": best, "parts": parts})

    improved = True
    while improved and evals < max_evals:
        improved = False
        for knob in knobs:
            if evals >= max_evals:
                break
            value = knob.get(current)
            for direction in (1, -1):
                trial_value = knob.moved(value, direction, steps[knob.name])
                if math.isclose(min(knob.hi, max(knob.lo, trial_value)), value):
                    continue
                trial = copy.deepcopy(current)
                knob.set(trial, trial_value)
                s, p = score(trial)
                if s < best - 1e-3:
                    best, parts, current = s, p, trial
                    improved = True
                    log(f"{knob.name} {value:g} -> {knob.get(trial):g}: {best:.2f}")
                    history.append(
                        {
                            "eval": evals,
                            "score": best,
                            "knob": knob.name,
                            "value": knob.get(trial),
                            "parts": parts,
                        }
                    )
                    break
            else:
                steps[knob.name] *= 0.5
        if not improved and any(steps[k.name] > k.step / 8 for k in knobs):
            improved = True  # keep going with smaller steps until they bottom out

    return TuneResult(current, best, parts, start, evals, history)
