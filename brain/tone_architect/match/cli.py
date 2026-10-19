"""tone-match: measure, compare, and tune patches against a reference recording.

    tone-match fingerprint ref.wav                     # what the analyzer hears
    tone-match compare ref.wav render.wav              # how far apart, and what's off
    tone-match tune --reference ref.wav --di di.wav --patch out/patch.json \\
        --manifest captures.manifest.json --out out/patch.tuned.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compare import distance, explain
from .fingerprint import fingerprint_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tone-match", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    fp = sub.add_parser("fingerprint", help="print a recording's tone fingerprint as JSON")
    fp.add_argument("wav", nargs="+")

    cmp_ = sub.add_parser("compare", help="distance between a reference and a candidate")
    cmp_.add_argument("reference")
    cmp_.add_argument("candidate")

    tn = sub.add_parser("tune", help="tune a patch's knobs so its render matches a reference")
    tn.add_argument("--reference", "-r", required=True, help="the guitar part to match (WAV)")
    tn.add_argument("--di", required=True, help="a dry guitar recording to play through the patch")
    tn.add_argument("--patch", "-p", required=True, help="starting patch.json")
    tn.add_argument("--manifest", "-m", default="captures.manifest.json")
    tn.add_argument("--out", "-o", default="out/patch.tuned.json")
    tn.add_argument("--max-evals", type=int, default=80, help="render budget (default 80)")
    tn.add_argument("--renderer", help="path to tone_render (default: plugin/render/.build)")

    args = parser.parse_args(argv)

    if args.command == "fingerprint":
        result = {path: fingerprint_file(path).to_dict() for path in args.wav}
        print(json.dumps(result if len(result) > 1 else next(iter(result.values())), indent=2))
        return 0

    if args.command == "compare":
        ref, cand = fingerprint_file(args.reference), fingerprint_file(args.candidate)
        total, parts = distance(ref, cand)
        print(f"distance {total:.2f}")
        for key, value in sorted(parts.items(), key=lambda kv: -kv[1]):
            print(f"  {key:<10} {value:.2f}")
        for note in explain(ref, cand):
            print(f"- {note}")
        return 0

    from .tune import make_render_fn, tune

    ref = fingerprint_file(args.reference)
    print(
        f"reference: delay {ref.delay_ms or 'none'} ms, modulation "
        f"{ref.mod_rate_hz or 'none'} Hz, tilt {ref.tilt_db_per_oct:+.2f} dB/oct",
        file=sys.stderr,
    )
    patch = json.loads(Path(args.patch).read_text())
    try:
        render = make_render_fn(
            Path(args.manifest).resolve(),
            Path(args.di).resolve(),
            Path(args.renderer) if args.renderer else None,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = tune(
        patch,
        ref,
        render,
        max_evals=args.max_evals,
        log=lambda line: print(f"  {line}", file=sys.stderr),
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tuned = result.patch
    tuned["created_by"] = "tone-match"
    out.write_text(json.dumps(tuned, indent=2) + "\n")
    report = out.with_suffix(".report.json")
    report.write_text(
        json.dumps(
            {
                "reference": args.reference,
                "start_score": result.start_score,
                "score": result.score,
                "parts": result.parts,
                "evaluations": result.evaluations,
                "history": result.history,
            },
            indent=2,
        )
        + "\n"
    )

    print(
        f"OK distance {result.start_score:.2f} -> {result.score:.2f} "
        f"in {result.evaluations} renders; wrote {out} (+ {report.name})"
    )
    final = render(tuned)
    for note in explain(ref, fingerprint_file(final)):
        print(f"- still off: {note}")
    final.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
