# supabase — optional cloud data source

Off by default. The brain runs entirely from a local manifest; this is for when you want your
capture catalog and recipe knowledge base in Postgres instead of a JSON file.

**Metadata only. Your `.nam` and `.wav` files never leave your machine** — the audio engine needs
local file access, and captures are large. `captures.file` is a path relative to your local
capture root.

## Apply the migration

```bash
psql "$DATABASE_URL" -f supabase/migrations/0001_init.sql
# or paste it into the Supabase SQL editor
```

Creates `captures` and `recipes` (both mirroring the schemas in `schema/` and
`recipes/recipes.seed.jsonl`), their indexes, and the pgvector extension.

## Use it

```bash
export SUPABASE_URL=https://<project>.supabase.co
export SUPABASE_KEY=<key>
export TONE_SOURCE=supabase

make db-sync    # idempotent upsert by id — safe to re-run
```

`tone-sync` derives a stable `id` for each recipe from artist + song + name, so re-syncing
updates rows rather than duplicating them.

`SUPABASE_KEY` is a password. Keep it in your shell profile or a gitignored `.env`; never commit
it, and prefer the anon key with row-level security over the service key.

## Same ranking, either source

`SupabaseLibrary` and `SupabaseRecipeSource` fetch rows and then run **the same Python scorer**
as the file-backed path (`retrieval/captures.py`, `retrieval/recipes.py`). Retrieval quality does
not change when you flip `TONE_SOURCE`, which is the point — the source is swappable, the
behaviour isn't.

## Semantic search (not wired yet)

The migration already creates `embedding vector(1536)` columns and the `match_captures` /
`match_recipes` cosine-distance RPCs, so enabling semantic retrieval later needs no migration.

1536 matches OpenAI `text-embedding-3-small`. If you use a different model, change the dimension
in **all four places** — both columns and both RPC signatures — and keep it consistent with
whatever you embed queries with. A dimension mismatch fails at query time, not at insert time.

Until then, keyword scoring is what runs, and no embeddings are computed or stored.
