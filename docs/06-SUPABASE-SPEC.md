# 06 · Supabase spec (optional cloud data source)

The user uses Supabase. It's the natural home for **capture metadata** and the **recipe knowledge
base**, with a clean upgrade path to pgvector semantic search. It's **opt-in** — the app defaults
to local JSON files, and both paths satisfy the same retrieval interface.

## What lives where

| Data | File source (default) | Supabase source |
|------|-----------------------|-----------------|
| Capture **metadata** (manifest) | `captures.manifest.json` | `captures` table |
| Recipe knowledge base | `recipes/recipes.seed.jsonl` | `recipes` table |
| Capture **files** (`.nam`/`.wav`) | local disk | **still local disk** |

The audio engine needs fast local file access, so the binaries always stay local; Supabase holds
metadata, and `captures.file` is a path relative to a local capture root the plugin resolves.

## Schema

Reproduce `docs/reference/supabase_schema.reference.sql` (put it at
`supabase/migrations/0001_init.sql`). It creates:
- `captures` — columns mirroring the manifest (`id` PK, `name`, `file`, `format`, `category`,
  `gain`, **`includes_cab`**, `character text[]`, `tags text[]`, `source`, `sample_rate`, `notes`),
  GIN indexes on tags/character, plus an optional `embedding vector(N)` column.
- `recipes` — `id` PK, `name`, `artist`, `song`, `tags text[]`, `description`, `chain_sketch text[]`,
  optional `embedding vector(N)`.
- `match_captures` / `match_recipes` RPCs for pgvector similarity (used only after you add
  embeddings; keyword scoring needs none).
Enables the `vector` extension. Pick the vector dimension to match whatever embedding model you
choose, and keep it consistent between the column and the RPCs.

## Retrieval integration

`SupabaseLibrary` and `SupabaseRecipeSource` fetch rows and reuse the **same Python scorer** as the
file path. Behavior is identical; only storage changes. The pipeline is unaware of the source. This
keeps ranking logic in one place and makes the file↔cloud switch a config flag (`TONE_SOURCE`).

## Sync

`tone-sync` upserts the local manifest + recipes into Supabase (idempotent, by `id`). Run it when
the library changes. Build the manifest locally first (via `tone-scaffold-manifest`), then publish.

## Upgrade to semantic search (later)

1. During sync, compute an embedding per capture/recipe (from name + character + tags +
   description) and write it to `embedding`.
2. In `SupabaseLibrary.search()` / `SupabaseRecipeSource.lookup()`, embed the request and call the
   `match_*` RPC instead of the keyword scorer.
Nothing upstream changes — the pipeline never knew how retrieval worked.

## TONE3000 API (evaluate — potential improvement)

TONE3000 exposes a public API (v1, OAuth 2.0 PKCE) with tone metadata, model file URLs, and search;
its `gears` parameter distinguishes `amp` vs `full-rig`. This could **replace filename inference for
`includes_cab`** and auto-populate the manifest/`captures` table directly from the user's TONE3000
account. Consider a `tone3000-sync` command parallel to `tone-sync`. Verify the current API surface
in the research checklist before building against it.

## Security

Treat `SUPABASE_KEY` like a password (never commit; keep in env). If a UI/endpoints are added
later, use Row Level Security and a restricted key.
