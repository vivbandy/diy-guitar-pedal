# Decisions log (ADR-style)

Research findings and design choices, especially deviations from the handoff brief. The Prime
Directives in `handoff/00-START-HERE.md` are intact throughout.

All entries dated 2026-08-06 come from working `handoff/08-RESEARCH-CHECKLIST.md` before writing
any code.

Format:

```
## <YYYY-MM-DD> — <short title>
- **Question / context:**
- **Finding (with source/date if searched):**
- **Decision:**
- **Rationale / impact:**
```

---

## 2026-08-06 — Cloud model id
- **Question:** Which Anthropic model should the cloud brain use, and is the Messages API request
  shape in the brief still current?
- **Finding:** Current model ids are `claude-opus-5`, `claude-fable-5`, `claude-sonnet-5`,
  `claude-haiku-4-5` (plus the 4.6/4.7/4.8 Opus line). Several request-shape details have moved:
  assistant **prefill now returns 400** on Opus 5 / Sonnet 5 / Fable 5 and the 4.6–4.8 family;
  `temperature`, `top_p`, `top_k` are rejected; `thinking.budget_tokens` is rejected in favour of
  `thinking={"type": "adaptive"}`; reasoning effort moved into `output_config.effort`.
- **Decision:** Default `DEFAULT_CLOUD_MODEL = "claude-opus-5"` in `config.py`, overridable with
  `TONE_CLOUD_MODEL`. `llm/cloud.py` sends adaptive thinking, `output_config.effort` (default
  `medium`), no sampling parameters, and no prefill.
- **Rationale / impact:** The brief's "don't hardcode a stale model" is honoured by pinning a
  current id *and* making it an environment variable, so the next drift is a config change, not a
  code change. Dropping prefill matters — the obvious way to force JSON-only output would now
  400.

## 2026-08-06 — Structured outputs cannot replace `validate.py`
- **Question:** Anthropic structured outputs (`output_config.format`) can constrain the response
  to a JSON Schema. Does that make the validator redundant?
- **Finding:** No. Structured outputs support types, `enum`, `const`, `anyOf`, `allOf`, `$ref`,
  and `additionalProperties: false`, but **do not support numeric constraints** (`minimum`,
  `maximum`, `multipleOf`) or string/array length constraints — the SDK strips them from the
  schema before sending. `oneOf` is also not in the supported set, and pydantic emits `oneOf` for
  discriminated unions.
- **Decision:** Use structured outputs for *shape* — `structured_output_schema()` derives the
  schema from the `Patch` model, rewrites `oneOf` → `anyOf`, strips the unsupported keywords, and
  forces `additionalProperties: false`. Keep `validate.py` and the bounded repair loop as the sole
  authority on ranges, capture existence, and cabinet pairing. `messages.create()` is used rather
  than `messages.parse()` so the validator (not the SDK) produces the error text that drives
  repair.
- **Rationale / impact:** Prime Directive 5 stands unchanged. A well-shaped patch with `mix: 4.2`
  is exactly the failure structured outputs cannot catch, and `tests/test_schema_sync.py` asserts
  none of the unsupported keywords survive sanitisation — so a schema change can't silently start
  returning 400s.

## 2026-08-06 — NAM Audio Unit baseline to fork  (deviation from the brief)
- **Question:** `05-PLUGIN-SPEC.md` prefers `Tr3m/nam-juce`. Is that still the best baseline?
- **Finding (GitHub API, 2026-08-06):**

  | | `sdatkinson/NeuralAmpModelerPlugin` | `Tr3m/nam-juce` |
  |---|---|---|
  | last push | 2026-06-12 | **2024-10-08** |
  | license | MIT | GPL-3.0 |
  | stars | 2,911 | 71 |
  | ships | NAM loader, IR convolution, noise gate, tone stack | NAM loader (self-described WIP) |
  | framework | iPlug2 | JUCE 8 |

  Other options considered and rejected: `mikeoliphant/neural-amp-modeler-lv2` (LV2, not AU),
  `rations/NAMix` (Linux VST3/standalone, GPL-3).
- **Decision:** **Deviate from the brief — fork `sdatkinson/NeuralAmpModelerPlugin`.**
- **Rationale / impact:** `nam-juce` has been dormant for ~22 months, and its GPL-3 licence is
  more restrictive than MIT for a fork. The original is actively maintained and already ships the
  IR convolver plus two of the eight effects, so it is also the shorter path to "a clean AU that
  loads a `.nam`". Consequence: the brief's JUCE research item is moot — iPlug2 comes with the
  baseline, and JUCE is no longer a dependency.

## 2026-08-06 — Plugin core is framework-free and independently testable
- **Question:** How much plugin code can be written and verified without the fork, given `cmake`
  is not installed on this machine?
- **Finding:** Apple clang 21 is available. The only genuinely framework-bound parts are the AU
  wrapper and the NAM/IR rendering; chain assembly and effect DSP need neither.
- **Decision:** Split `plugin/src` so that `PatchSpec`, `Manifest`, `ChainHost`, `effects/*` and
  `transport/*` depend on nothing but the standard library, with JSON isolated in `PatchLoader.cpp`
  and `ManifestJson.cpp`. `nam_capture` / `ir_cab` are recorded as `CaptureSlot`s with a chain
  position rather than implemented as effects. `plugin/tests/run.sh` compiles and runs 107 checks
  with `clang++` alone.
- **Rationale / impact:** Most of Phase 2 is now real, reviewed, compiling code instead of a
  paper spec, and the fork's diff stays small. What remains genuinely unbuilt is the AU wrapper
  and the NAM/IR splice — flagged as such in `plugin/README.md` and the top-level README.

## 2026-08-06 — TONE3000 API integration
- **Question:** Integrate the TONE3000 API now to populate the manifest and `includes_cab`, or
  defer to filename inference?
- **Finding (tone3000.com/api + `tone-3000/api` client, 2026-08-06):** Base
  `https://www.tone3000.com/api/v1`, OAuth 2.0 + PKCE, bearer token, 100 req/min. Endpoints
  include `/tones/search`, `/tones/favorited`, `/tones/created`, `/tones/{id}`, `/models`
  (`tone_id`, `page`, `page_size`, `architecture`; carries `model_url`). **The `gears` values have
  changed since the brief: it is now `amp`, `amp-cab`, `cab`, `pedal`, `outboard`, `space`,
  `experimental` — `full-rig` is a deprecated alias for `amp-cab`.** `architecture` is `1` (A1),
  `2` (A2), or `custom`.
- **Decision:** Integrate now as an optional `tone3000-sync` command. `includes_cab` is set from
  `gear ∈ {amp-cab, full-rig}` and `category` from the same field; both spellings are accepted so
  older records still map correctly. Auth is a bearer token from `TONE3000_TOKEN`; the OAuth PKCE
  dance is left to the user's own flow.
- **Rationale / impact:** `includes_cab` is a *correctness* rule (Prime Directive 4), and
  inferring it from a filename is a guess that silently produces thin tones. Taking it from the
  API removes the guess. Filename inference stays in `scaffold_manifest.py` for people who don't
  use TONE3000, but it marks every amp entry with a "CHECK includes_cab" note.

## 2026-08-06 — NAM architecture A2
- **Question:** Does the chosen baseline support the current `.nam` format?
- **Finding:** A2 is a new architecture, not a format bump, and needs **NeuralAmpModelerCore
  ≥ v0.5.2**. A1 (standard/lite/feather/nano) models keep working.
- **Decision:** Note the ≥ v0.5.2 requirement in `plugin/README.md` as a submodule check after
  forking; expose `--architecture` on `tone3000-sync` so a library can be pinned to A1 or A2.
- **Rationale / impact:** No brain-side impact — the manifest records `format: nam` regardless of
  architecture. It is purely a plugin submodule-pin concern.

## 2026-08-06 — Local backend uses a JSON Schema, not the GBNF grammar
- **Question:** Is hand-written GBNF still the best way to constrain a local model?
- **Finding:** `llama-server`'s OpenAI-compatible `/chat/completions` now accepts
  `response_format: {"type": "json_schema", "json_schema": {...}}` and converts the schema to a
  grammar internally. Raw `grammar` is still supported.
- **Decision:** Default the local backend to `response_format` with the same sanitised schema the
  cloud backend uses. `prompts/grammar/patch.gbnf` is preserved and selected by
  `TONE_LOCAL_GRAMMAR=1`.
- **Rationale / impact:** One schema now drives both backends, so the constraint can't drift from
  the contract the way a hand-maintained grammar does. Grammar-constrained decoding is still what
  runs — this only changes who writes the grammar. The brief's "keep grammar-constrained decoding
  unless something clearly better exists" is satisfied.

## 2026-08-06 — Supabase and the embedding dimension
- **Question:** Is the reference SQL current, and what embedding dimension should the vector
  columns use?
- **Finding:** pgvector is available on Supabase and supports the reference schema as written.
  `vector(1536)` matches OpenAI `text-embedding-3-small`; other models differ (Gemini 3072,
  gte-small 384).
- **Decision:** Ship `supabase/migrations/0001_init.sql` unchanged from the reference, including
  the `vector(1536)` columns and the `match_captures` / `match_recipes` RPCs. **Do not compute
  embeddings in v1** — keyword scoring is what runs on both sources.
- **Rationale / impact:** The columns and RPCs cost nothing unused and mean enabling semantic
  search later needs no migration. `supabase/README.md` warns that changing the dimension means
  changing it in all four places.

## 2026-08-06 — Speech-to-text (Phase 3)
- **Question:** Best current local STT for voice input?
- **Finding:** **Not verified.** Deferred rather than researched, since Phase 3 voice input is
  explicitly optional and nothing in Phases 0–2 depends on it.
- **Decision:** Defer. Assume whisper.cpp or its successor and re-check when Phase 3 starts.
- **Rationale / impact:** Recorded as an open assumption rather than a finding, per the
  checklist's "if you cannot verify an item, proceed and note the assumption".

## 2026-08-06 — Schema shape kept as-is
- **Question:** The checklist invites evolving the JSON Schema if research suggests a better
  shape. Should it change?
- **Decision:** No change. `schema/patch.schema.json` and `schema/capture.manifest.schema.json`
  are copied verbatim from `docs/reference/` and are the source of truth; `models.py` mirrors
  them and `tests/test_schema_sync.py` asserts the two agree on both valid and invalid patches.
- **Rationale / impact:** Nothing in the research argued for a different shape, and the schema is
  the contract both halves are written against. The only schema-adjacent addition is a
  *derived*, sanitised copy for the structured-outputs API — the canonical file is untouched.

## 2026-08-06 — Toolchain: Python 3.13 + uv
- **Question:** The brief requires Python 3.11+; the system Python is 3.9.6.
- **Finding:** `python3.13` and `uv` are installed via Homebrew; 3.11 and 3.12 are not. `cmake` is
  **not** installed.
- **Decision:** Build and test on 3.13 while `pyproject.toml` declares `requires-python = ">=3.11"`.
  The `Makefile` defaults `PYTHON ?= python3.13` and uses `venv` + `pip` so it works without `uv`.
  `cmake` was **not** installed — an unprompted package install is not something to do silently
  given the active supply-chain advisory, and Phases 0–1 don't need it.
- **Rationale / impact:** Phases 0 and 1 are fully runnable. The only consequence of the missing
  `cmake` is that the AU wrapper can't be compiled here; `plugin/tests/run.sh` deliberately uses
  `clang++` directly so the plugin core is still verified.

## 2026-08-06 — Cloud path not exercised end-to-end
- **Question:** Does the whole pipeline work against the real API?
- **Finding:** No Anthropic credentials are available on this machine (`ANTHROPIC_API_KEY` unset,
  no `ant auth login` profile), so a live generation was never run.
- **Decision:** Ship it untested against the live API and say so plainly. The pipeline, repair
  loop, and validator are covered by `FakeLLM`-driven tests; `CloudLLM` now fails with a clear
  message instead of an SDK traceback when credentials are missing.
- **Rationale / impact:** The first real run may surface a request-shape mismatch. If
  `output_config` is rejected, `CloudLLM.complete` already falls back to a prompt-only JSON
  request, so a shape change degrades rather than breaks.
