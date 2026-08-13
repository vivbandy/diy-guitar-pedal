from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Config
from .library import ManifestLibrary, make_library
from .recipe_source import default_recipes_path, make_recipe_source
from .validate import json_schema_errors, validate_patch


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tone-architect",
        description="Turn a natural-language tone request into a validated patch.json.",
    )
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="generate a patch from a tone request")
    _add_generate_args(gen)

    val = sub.add_parser("validate", help="validate an existing patch against a manifest")
    val.add_argument("patch", help="path to a patch.json")
    val.add_argument("--manifest", "-m", required=True, help="path to a capture manifest")
    val.add_argument(
        "--strict",
        action="store_true",
        help="also check the canonical JSON Schema in schema/, not just the pydantic models",
    )

    return parser


def _add_generate_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("request", help="the tone you want, in plain English")
    p.add_argument("--manifest", "-m", help="path to a capture manifest (file source)")
    p.add_argument("--out", "-o", default="out/patch.json", help="where to write the patch")
    p.add_argument("--recipes", help="path to recipes.seed.jsonl (defaults to the repo copy)")
    p.add_argument("--print", dest="show", action="store_true", help="print the patch to stdout")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in {"generate", "validate", "-h", "--help"}:
        argv.insert(0, "generate")

    args = _build_parser().parse_args(argv)
    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "generate":
        return _cmd_generate(args)
    _build_parser().print_help()
    return 2


def _cmd_validate(args: argparse.Namespace) -> int:
    library = ManifestLibrary.from_path(args.manifest)
    raw = json.loads(Path(args.patch).read_text())

    problems: list[str] = []
    if args.strict:
        problems += [f"[json-schema] {e}" for e in json_schema_errors(raw)]

    result = validate_patch(raw, library)
    problems += result.errors

    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if problems:
        print(f"INVALID  {args.patch}", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print(f"OK  {args.patch}  ({len(result.patch.chain)} nodes)")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    from .llm.factory import make_llm
    from .pipeline import run

    config = Config.load()
    try:
        library = make_library(config, args.manifest)
        recipes = make_recipe_source(config, args.recipes or default_recipes_path())
        llm = make_llm(config)
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    result, path = run(args.request, library, llm, args.out, config=config, recipes=recipes)

    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if not result.ok:
        print(f"FAILED after {result.attempts} attempt(s):", file=sys.stderr)
        for e in result.errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"OK  wrote {path}  ({result.attempts} attempt(s), {len(result.patch.chain)} nodes)")
    if args.show:
        print(json.dumps(result.patch.model_dump(mode="json", exclude_none=True), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
