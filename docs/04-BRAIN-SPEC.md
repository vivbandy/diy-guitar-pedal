# 04 · Brain spec (Python pipeline)

The Python half. Turns a natural-language request into a validated `patch.json`. Build this first —
it's the user's wheelhouse and delivers value before any C++ exists.

## Package layout (suggested)

```
brain/
  pyproject.toml            # package "tone-architect", py>=3.11, deps: pydantic, jsonschema
                            # extras: [cloud]=anthropic, [supabase]=supabase, [dev]=pytest,ruff
                            # console scripts: tone-architect, tone-sync, tone-scaffold-manifest
  README.md                 # install + run + local-backend notes
  tone_architect/
    __init__.py
    config.py               # env-driven Config (backend, model, source, supabase creds, limits)
    models.py               # pydantic v2 models mirroring the schema (keep field names identical)
    library.py              # CaptureLibrary protocol; ManifestLibrary (file) + SupabaseLibrary; make_library()
    recipe_source.py        # RecipeSource protocol; File + Supabase; make_recipe_source()
    validate.py             # schema + capture existence + CAB PAIRING + tone-core; repair-friendly errors
    preset_writer.py        # atomic write (temp file + os.replace)
    pipeline.py             # parse -> retrieve -> generate -> validate(+repair) -> write
    cli.py                  # `tone-architect "<req>" --manifest <m> --out <p>` + `validate` subcommand
    scaffold_manifest.py    # scan a captures folder -> manifest stub (guesses category/gain/includes_cab)
    sync.py                 # push local manifest + recipes into Supabase (idempotent upsert)
    llm/
      base.py               # LLMClient protocol: complete(system, user) -> str
      cloud.py              # Anthropic backend (lazy import; JSON-only prompt)
      local.py              # llama.cpp OpenAI-compatible backend; applies patch.gbnf grammar
      factory.py            # make_llm(config)
    retrieval/
      captures.py           # keyword/tag/gain scorer over the manifest; guarantees amp + cab candidates
      recipes.py            # keyword scorer over recipes; expose score_rows() for reuse
    prompts/
      system_parse.md       # THE system prompt (canonical copy in docs/reference/system_parse.md)
      grammar/patch.gbnf    # canonical copy in docs/reference/patch.gbnf
  tests/
    conftest.py, test_validate.py, test_pipeline.py
```

## Pipeline stages

- **parse/retrieve** live in `_build_user_message`: fetch candidate captures (`library.search`) and
  recipe hints (`recipe_source.lookup`), format them into the user message alongside the request.
  Only pass captures that exist; instruct the model to choose `capture_id` from that list only.
- **generate**: call the LLM with `system_parse.md` + the built user message. Cloud backend for
  quality; local backend forces JSON via the GBNF grammar.
- **validate + repair**: run `validate_patch`. On failure, append the plain-English error to the
  user message and retry, up to `max_repair_attempts` (default 2). Return the first valid patch or
  a failure with the last error.
- **write**: atomic write to the output path (also the path the plugin can watch).

## Validation (reproduce `docs/reference/validate_reference.py` behavior exactly)

Gates, in order: (1) structural via pydantic; (2) every `capture_id` exists in the library;
(3) at least one tone core; (4) **cabinet pairing** — amp-head without a following `ir_cab` is a
hard error ("would sound thin"), full-rig with an `ir_cab` is a non-fatal warning ("double cab").
Errors are written for a model to read and fix. `ValidationResult` carries `ok`, `patch`, `errors`,
`warnings`. Surface warnings in the CLI even on success.

## The system prompt

Use `docs/reference/system_parse.md` verbatim as the starting point. It already teaches: use only
listed captures; always include a tone core; the amp-head/full-rig cabinet rule; signal-flow order;
parameter sanity; JSON-only output. Improve wording if your testing shows the current model needs
it, but keep the cabinet rule and the "select only from provided captures" constraint prominent.

## LLM backends

- `LLMClient` protocol: `complete(system: str, user: str) -> str`.
- Cloud: Anthropic Messages API. **Do not hardcode a stale model id** — read the current
  recommended model from config and confirm the current id via the research checklist. Prompt for
  JSON-only; concatenate text blocks.
- Local: llama.cpp server (OpenAI-compatible). Pass the GBNF grammar to constrain output. This is
  the offline path; small models are unreliable at free-form JSON without it.

## Config (env-driven)

`TONE_BACKEND` (cloud|local), cloud model id, `ANTHROPIC_API_KEY`, local URL/model, `TONE_SOURCE`
(file|supabase), `SUPABASE_URL`/`SUPABASE_KEY`, repair/candidate/recipe limits. Frozen dataclass;
`Config.load()`.

## Retrieval

Keyword/tag/gain scoring over the manifest; **guarantee an amp and at least one cab IR appear in
candidates** (so the model can satisfy the cabinet rule). Recipes: keyword overlap over
`recipes.seed.jsonl`. Factor scoring so the Supabase sources reuse it. Both are seams for a later
pgvector/embedding upgrade behind unchanged signatures.

## Tests (keep green)

- valid example patch passes; unknown `capture_id` rejected; out-of-range param rejected; missing
  tone core rejected; malformed JSON rejected.
- **cabinet pairing**: amp-head without cab IR rejected; amp-head with cab IR ok; full-rig without
  IR ok; full-rig with IR warns.
- pipeline with a fake LLM: valid on first try; and a repair-loop test (first output broken/thin,
  second output valid).

## CLI & tooling

- `tone-architect "<request>" --manifest <m> --out <p>` and `tone-architect validate <patch>
  --manifest <m>`. When `TONE_SOURCE=supabase`, `--manifest` is optional.
- `tone-scaffold-manifest <captures_dir> -o <manifest.json>` — scans `.nam`/`.wav`, pre-fills
  `id`/`name`/`file`/`format`, guesses `category`/`gain`/`includes_cab` from filenames, leaves
  `character`/`tags` empty for the user.
- `tone-sync all --manifest <m> --file <recipes.jsonl>` — idempotent upsert into Supabase.
