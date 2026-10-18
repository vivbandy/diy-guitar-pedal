# brain — the Python half

Turns a natural-language tone request into a validated `patch.json`. Runs entirely off the audio
thread; its only output is a file.

```
parse → retrieve → generate → validate (+repair) → write preset
```

## Install

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e "brain[cloud,dev]"     # add local,supabase,tone3000 as needed
```

Extras: `cloud` (Anthropic), `local` (llama-server via httpx), `supabase`, `tone3000`, `dev`.

## Commands

| Command | What it does |
|---|---|
| `tone-architect "<request>" -m <manifest> -o <out>` | generate a patch |
| `tone-architect validate <patch> -m <manifest> [--strict]` | validate an existing patch |
| `tone-scaffold-manifest <folder> -o <manifest>` | scan a captures folder into a manifest stub |
| `tone-architect "<request>" --discover [-m <manifest>] [--download]` | find gear on TONE3000, then generate |
| `tone3000-download [-m <manifest>]` | fetch model files for TONE3000 captures not yet on disk |
| `tone3000-login [--logout]` | sign in to TONE3000 (device code; needs `TONE3000_CLIENT_ID`) |
| `tone3000-sync --scope favorited --merge` | build a manifest from the TONE3000 API |
| `tone-sync --manifest <m> --recipes <r>` | idempotent upsert into Supabase |

`--strict` on `validate` additionally checks the canonical JSON Schema in `schema/`, not just the
pydantic mirror.

## Layout

```
tone_architect/
  config.py            env-driven frozen Config; holds no secret
  models.py            pydantic v2 mirror of the two JSON Schemas
  schema_files.py      locates schema/ (repo root is the single source of truth)
  validate.py          structure → capture existence → tone core → cabinet pairing
  preset_writer.py     atomic write (temp file + os.replace)
  pipeline.py          the five stages; parse+retrieve live in _build_user_message
  cli.py               generate / validate
  library.py           CaptureLibrary protocol; ManifestLibrary + SupabaseLibrary
  recipe_source.py     RecipeSource protocol; File + Supabase + Null
  scaffold_manifest.py filename inference for a manifest stub
  tone3000.py          TONE3000 API -> manifest (authoritative includes_cab)
  discover.py          --discover: gear plan -> TONE3000 search -> candidates; saves what's used
  tone3000_auth.py     tone3000-login: OAuth device sign-in, stored + auto-refreshed token
  sync.py              manifest + recipes -> Supabase
  llm/
    base.py            LLMClient protocol: complete(system, user) -> str
    cloud.py           Anthropic; structured outputs
    local.py           llama-server; JSON Schema or GBNF grammar
    factory.py         make_llm(config)
  retrieval/
    captures.py        keyword/tag/gain scorer; guarantees amp + cab candidates
    recipes.py         keyword scorer; score_rows() is reused by the Supabase source
  prompts/
    system_parse.md    the canonical system prompt
    grammar/patch.gbnf GBNF fallback for the local backend
```

## Validation

Four gates, in order. The first failure short-circuits and its message is what gets fed back to
the model for repair.

1. **Structure** — `Patch.model_validate`: node types, required fields, parameter ranges.
2. **Existence** — every `capture_id` is in the user's library. *The model selects; it never
   invents.* The error names the ids that were actually available.
3. **Tone core** — at least one `nam_capture` or `ir_cab`, or there is no sound.
4. **Cabinet pairing** — an enabled amp-head capture with no enabled `ir_cab` anywhere in the
   chain is an **error**; a full rig plus an `ir_cab` is a **warning** (double-cab). Presence, not
   position — the plugin owns ordering.

## The repair loop

`generate_patch` runs `max_repair_attempts + 1` times (default 3 total). On failure the previous
output and the validator's errors are appended to the same user message and sent back. It is
bounded on purpose: an unbounded loop against a paid API is a bill, not a feature.

## Why validation survives structured outputs

The cloud backend uses `output_config.format` with a JSON Schema derived from the `Patch` model,
which guarantees well-formed JSON and correct node shapes. But the structured-outputs API **does
not support numeric constraints** — `minimum`/`maximum` are stripped before the schema is sent.
So the API can hand back a `mix` of 4.2 in a perfectly-shaped patch. `validate.py` is what catches
that, and the same code catches it on the local backend too.

`tests/test_schema_sync.py` asserts the sanitised schema contains none of the unsupported
keywords, so a future model change can't silently start 400-ing.

## Swapping the halves

Three seams, all behind protocols, all switched by environment variable:

| Seam | Env | Options |
|---|---|---|
| LLM | `TONE_BACKEND` | `cloud` (Anthropic) / `local` (llama-server) |
| Capture + recipe data | `TONE_SOURCE` | `file` / `supabase` |
| Transport | — | atomic file write today; OSC is a Phase 3 plugin-side concern |

## Tests

```bash
cd brain && ../.venv/bin/python -m pytest -q
```

44 tests. `FakeLLM` in `conftest.py` makes the pipeline tests deterministic and free — no network,
no key.
