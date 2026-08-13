"""Push the local manifest + recipes into Supabase (metadata only — binaries stay local)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Config
from .validate import load_manifest


def _client(config: Config):
    if not (config.supabase_url and config.supabase_key):
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")
    from supabase import create_client

    return create_client(config.supabase_url, config.supabase_key)


def sync_captures(client, manifest_path: str | Path) -> int:
    manifest = load_manifest(manifest_path)
    rows = [c.model_dump(mode="json", exclude_none=True) for c in manifest.captures]
    if rows:
        client.table("captures").upsert(rows, on_conflict="id").execute()
    return len(rows)


def sync_recipes(client, recipes_path: str | Path) -> int:
    rows = []
    for line in Path(recipes_path).expanduser().read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row.setdefault("id", _recipe_id(row))
        rows.append(row)
    if rows:
        client.table("recipes").upsert(rows, on_conflict="id").execute()
    return len(rows)


def _recipe_id(row: dict) -> str:
    import re

    basis = " ".join(x for x in (row.get("artist"), row.get("song"), row.get("name")) if x)
    return re.sub(r"[^a-z0-9]+", "_", basis.lower()).strip("_") or "recipe"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tone-sync", description="Upsert manifest + recipes into Supabase (idempotent)."
    )
    parser.add_argument("--manifest", "-m", help="capture manifest to push")
    parser.add_argument("--recipes", "-r", help="recipes.seed.jsonl to push")
    args = parser.parse_args(argv)

    if not args.manifest and not args.recipes:
        parser.error("give --manifest and/or --recipes")

    try:
        client = _client(Config.load())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.manifest:
        print(f"captures: upserted {sync_captures(client, args.manifest)}")
    if args.recipes:
        print(f"recipes:  upserted {sync_recipes(client, args.recipes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
