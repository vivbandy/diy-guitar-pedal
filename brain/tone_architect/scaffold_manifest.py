"""Scan a captures folder and emit a manifest stub.

Filename inference is a starting point only — `includes_cab` in particular is a correctness rule,
so every amp entry must be checked by hand (or populated from TONE3000 via `tone3000-sync`, which
knows the amp/amp-cab distinction authoritatively).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .models import Capture, CaptureCategory, CaptureFormat, CaptureGain, CaptureManifest

_GAIN_HINTS: list[tuple[CaptureGain, tuple[str, ...]]] = [
    (CaptureGain.fuzz, ("fuzz", "muff")),
    (CaptureGain.high_gain, ("high_gain", "highgain", "metal", "rectifier", "djent")),
    (CaptureGain.mid_gain, ("mid_gain", "midgain", "lead", "drive", "od", "overdrive")),
    (CaptureGain.crunch, ("crunch", "breakup", "edge")),
    (CaptureGain.clean, ("clean",)),
]

_PEDAL_HINTS = ("pedal", "ts808", "tubescreamer", "screamer", "klon", "muff", "fuzz", "boost")
_CAB_HINTS = ("cab", "_ir", "ir_", "impulse", "412", "212", "112", "speaker")
_OUTBOARD_HINTS = ("outboard", "console", "preamp_1073", "eq_", "comp_", "1176", "la2a")
_FULL_RIG_HINTS = ("fullrig", "full_rig", "amp_cab", "ampcab", "combo", "full-rig")


def slugify(stem: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    return slug or "capture"


def infer(path: Path) -> Capture:
    stem = path.stem
    lowered = stem.lower()
    fmt = CaptureFormat.wav_ir if path.suffix.lower() == ".wav" else CaptureFormat.nam

    if fmt is CaptureFormat.wav_ir or any(h in lowered for h in _CAB_HINTS):
        category = CaptureCategory.cab
    elif any(h in lowered for h in _OUTBOARD_HINTS):
        category = CaptureCategory.outboard
    elif any(h in lowered for h in _PEDAL_HINTS):
        category = CaptureCategory.pedal
    else:
        category = CaptureCategory.amp

    gain = CaptureGain.n_a
    if category is not CaptureCategory.cab:
        for candidate, hints in _GAIN_HINTS:
            if any(h in lowered for h in hints):
                gain = candidate
                break

    includes_cab = category is CaptureCategory.amp and any(h in lowered for h in _FULL_RIG_HINTS)

    return Capture(
        id=slugify(stem),
        name=stem.replace("_", " ").strip(),
        file=path.name,
        format=fmt,
        category=category,
        gain=gain,
        includes_cab=includes_cab,
        notes=None
        if category is not CaptureCategory.amp
        else "CHECK includes_cab by ear or via TONE3000",
    )


def scaffold(folder: Path, root: str | None = None) -> CaptureManifest:
    files = sorted(
        p
        for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in {".nam", ".wav"} and not p.name.startswith(".")
    )
    captures: list[Capture] = []
    seen: set[str] = set()
    for f in files:
        cap = infer(f)
        base = cap.id
        n = 2
        while cap.id in seen:
            cap = cap.model_copy(update={"id": f"{base}_{n}"})
            n += 1
        seen.add(cap.id)
        captures.append(cap)
    return CaptureManifest(root=root or str(folder), captures=captures)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tone-scaffold-manifest",
        description="Scan a captures folder and write a manifest stub for hand-editing.",
    )
    parser.add_argument("folder", help="folder containing .nam / .wav captures")
    parser.add_argument("--out", "-o", default="captures.manifest.json")
    parser.add_argument("--root", help="value for the manifest's `root` field")
    args = parser.parse_args(argv)

    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        print(f"not a folder: {folder}", file=sys.stderr)
        return 1

    manifest = scaffold(folder, root=args.root)
    payload = manifest.model_dump(mode="json", exclude_none=True)
    Path(args.out).expanduser().write_text(json.dumps(payload, indent=2) + "\n")

    amps = sum(1 for c in manifest.captures if c.category is CaptureCategory.amp)
    print(f"wrote {args.out}: {len(manifest.captures)} captures")
    if amps:
        print(f"  review `includes_cab` on all {amps} amp entries — it is a correctness rule")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
