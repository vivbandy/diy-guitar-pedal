# 02 · Architecture

## The core split

Two halves that communicate only through a `patch.json` file conforming to the schema in
`docs/reference/patch.schema.json`. They never share a thread.

```
┌─────────────────────────────┐         ┌──────────────────────────────┐
│  BRAIN  (Python, off-line)  │         │  PLUGIN  (JUCE AU, real-time) │
│                             │  patch  │                              │
│  request ─▶ parse           │  .json  │   watch/load ─▶ build chain  │
│         ─▶ retrieve  ───────┼────────▶│            ─▶ processBlock()  │
│         ─▶ generate (LLM)   │         │               (audio thread)  │
│         ─▶ validate(+repair)│         │                              │
│         ─▶ write preset     │         │                              │
└─────────────────────────────┘         └──────────────────────────────┘
        not real-time                          hard real-time
```

## The contract: `patch.json`

A patch is an **ordered signal chain** of typed nodes. One node type is `nam_capture` (amp/cab
core); another is `ir_cab` (cabinet IR); the rest are effects (drive, compressor, noise_gate, eq,
delay, reverb, modulation, filter). Order = signal-flow order. Captures are referenced by
`capture_id` (an indirection into the user's manifest), never by raw path — this keeps patches
portable and lets validation guarantee the model only used captures that exist.

The canonical schema is `docs/reference/patch.schema.json`. The capture manifest schema (the
library catalog, including the `includes_cab` flag) is `docs/reference/capture.manifest.schema.json`.
Worked examples: `patch.example.gilmour.json` (amp-head + cab IR) and `patch.example.srv.json`
(full-rig, no IR). Study those two — they demonstrate both sides of the cabinet rule.

## Brain pipeline (modular, swappable stages)

1. **parse** — request → intent (artist/song/genre/descriptors).
2. **retrieve** — grounding:
   - recipes: nearest curated tone recipes (keyword now; embeddings later).
   - captures: candidate captures from the manifest by tag/character/gain match. **Always include
     an amp and ≥1 cab IR** among candidates so the model can pair an amp head.
3. **generate** — LLM composes the patch, constrained to available `capture_id`s. Cloud model for
   quality; local llama.cpp option using a GBNF grammar (`docs/reference/patch.gbnf`) to force
   valid JSON from small models.
4. **validate** — structural (schema/pydantic) + semantic (capture existence) + **cabinet pairing**
   + tone-core presence. On failure, a plain-English error feeds a bounded repair loop.
5. **write preset** — atomic write (temp + rename) to the path the plugin watches.

The full validation logic — including the cab-pairing algorithm and the warning for double-cabbing
— is provided verbatim in `docs/reference/validate_reference.py`. Reproduce its behavior.

## Data source abstraction (file ↔ Supabase)

Captures and recipes can be backed by **local JSON** (default, zero setup) or **Supabase**
(`TONE_SOURCE=supabase`). Both satisfy the same small interface — a capture library exposes
`ids()`, `by_id()`, `search()`; a recipe source exposes `lookup()`. The Supabase implementations
fetch rows and reuse the *same* Python scorer as the file path, so behavior is identical and
ranking logic lives in one place. Only metadata lives in Supabase; `.nam`/`.wav` files stay local.
(See `06-SUPABASE-SPEC.md`.)

## Plugin (real-time host)

One self-contained AU = one complete patch. A plugin cannot instantiate other plugins in the DAW
(sandbox boundary), so the effects chain lives **inside** this plugin. Fork an existing open-source
NAM AU (it already loads `.nam` and has an IR loader), add the effects chain and a patch loader.
Patch loading happens on the message thread with an atomic hand-off to the audio thread; nothing
slow or allocating touches `processBlock`. (See `05-PLUGIN-SPEC.md`.)

## Extensibility seams (design these in)

- **New effect type** → schema `$def` + pydantic model + plugin DSP block + an example. Nothing
  else changes.
- **New LLM backend** → implement the client protocol.
- **New data source** → implement the library / recipe-source interface.
- **New transport** → implement the patch-source interface; plugin loader stays transport-agnostic.
- **Voice input** → prepend a speech-to-text step producing the request string. No other change.
- **Semantic retrieval** → swap keyword scoring for pgvector behind the same `search()`/`lookup()`.

## Key architectural decisions (record equivalents in DECISIONS.md)

- AU-only target (Logic/GarageBand constraint).
- Brain decoupled from plugin via a JSON patch contract.
- Effects chain hosted inside one plugin instance (no host-level multi-plugin orchestration).
- `capture_id` indirection instead of raw paths.
- `includes_cab` metadata + validator-enforced cabinet pairing.
- Metadata in Supabase (optional), binaries local.
