# 07 · Build roadmap

Build in phases; each ends in something that runs and is committed. Do the research checklist
(`08`) first and set up git (`09`) before Phase 0.

## Phase 0 — Contract & brain skeleton (no audio)

Goal: produce real, validated `patch.json` from hand-written intent. Proves the data model.

- Copy the canonical schemas into `schema/`. Mirror them in `brain/tone_architect/models.py`.
- Implement `validate.py` (schema + capture existence + cabinet pairing + tone core) per
  `docs/reference/validate_reference.py`.
- Implement `preset_writer.py` (atomic write).
- Tests: valid example passes; unknown capture rejected; out-of-range rejected; missing core
  rejected; malformed JSON rejected; **all four cab-pairing cases**.
- `tone-architect validate <patch> --manifest <m>` works end to end.

**Exit:** `pytest` green; the two example patches validate against the example manifest.

## Phase 1 — Brain end-to-end (cloud LLM)

Goal: type a request, get a valid patch.

- `llm/base.py` + `llm/cloud.py` (current Anthropic model, confirmed via research).
- `retrieval/captures.py` (+ guarantee amp & cab candidates) and `retrieval/recipes.py`.
- `pipeline.py`: parse → retrieve → generate → validate(+repair) → write.
- Copy `system_parse.md` and `patch.gbnf` in; wire the repair loop.
- Seed `recipes/recipes.seed.jsonl` (reference copy provided; keep/extend it).
- Scaffolder + Supabase source + sync (can slot here or Phase 1.5).

**Exit:** several varied requests each yield musically reasonable, schema-valid, cabinet-correct
patches. Load one manually in Logic (NAM AU + stock effects) to sanity-check the tone.

## Phase 2 — Plugin: one AU = one patch

- Fork the chosen NAM AU; confirm a clean AU build loading a `.nam` in Logic.
- Add the effects-chain framework + effects (drive → eq → compressor → delay → reverb →
  modulation → gate → filter).
- Implement the patch loader: parse, resolve `capture_id`, build chain off the audio thread,
  atomic swap. "Load Patch…" file picker first.

**Exit:** insert the AU, load `patch.example.gilmour.json`, hear amp head → cab IR → delay → reverb
with no dropouts.

## Phase 3 — Live loop + polish

- Plugin transport: watch a path (brain writes there); optional OSC for instant push.
- Brain `--watch` dev mode writing to that path.
- Optional: in-plugin request UI (web view); local llama.cpp backend + GBNF; voice via speech-to-text.

**Exit:** type/speak a tone → it loads live → record with it.

## Cross-cutting (always)

- Keep schema ↔ `models.py` in sync (add a test asserting agreement).
- New effect type touches: schema `$def`, pydantic model, plugin DSP block, an example.
- New capture/recipe field touches: schema, pydantic model, AND the Supabase migration.
- Never regress the Prime Directives (`00-START-HERE.md`).
- Keep both data sources (file/Supabase) working.

## Suggested first commit

Repo skeleton + `docs/` + copied contracts + Phase 0 brain (models + validate + tests passing).
