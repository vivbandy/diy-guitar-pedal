# 00 · START HERE — build runbook for Claude Code

You (Claude Code) are being handed a complete design brief and asked to **build the project from
scratch**, then **push it to GitHub**. This file is your runbook. Read every doc in this `docs/`
folder before writing code — they are ordered and cross-referenced.

## The project in one sentence

An LLM-driven guitar tone tool: the user describes a tone in plain English (*"Gilmour's lead from
Comfortably Numb"*) and the system assembles a complete, playable signal chain (amp capture + cab
IR + effects) from the user's own library, delivered as a patch that loads in Logic Pro /
GarageBand.

## Coordinates

- **Local working directory:** `~/src/diyguitarproject`
- **Git remote:** `https://github.com/vivbandy/diy-guitar-pedal.git`
- **Target platform for the audio plugin:** macOS, Audio Unit (Logic Pro + GarageBand)
- **User background:** strong Python + API skills; uses Supabase; hobby project.

## Prime directives (do not violate — these are load-bearing design decisions)

1. **Temporal decoupling.** The LLM ("brain") and the audio engine ("plugin") never share a
   thread. The brain produces a validated `patch.json`; the plugin loads it. Nothing slow ever
   touches the audio thread. (See `02-ARCHITECTURE.md`.)
2. **Audio Unit only.** Logic/GarageBand load AU, not VST. The plugin must build as an AU.
3. **The model selects; it never invents.** Every capture referenced in a patch must exist in the
   user's library. Validation rejects unknown captures.
4. **Cabinet pairing is a correctness rule.** An amp-HEAD capture (no built-in cab) must be paired
   with a cab IR or the tone is thin/harsh; a full-rig capture must not be double-cabbed.
   Validation enforces this. (See `01-CONTEXT-AND-VISION.md` §Domain and `04-BRAIN-SPEC.md`.)
5. **Validate every patch** before it leaves the brain, with a bounded generate→validate→repair
   loop.
6. **Keep the halves swappable.** Cloud vs local LLM, file vs Supabase data source, file-watch vs
   OSC transport — all behind interfaces.

## Order of operations

1. **Read all docs** in this folder (00→09) plus `docs/reference/` (the canonical, verbatim
   artifacts — schema, prompt, examples, validation logic).
2. **Run the research checklist** (`08-RESEARCH-CHECKLIST.md`) *before building*. This design was
   drafted from information current as of early 2026. Verify the current state of the ecosystem
   (NAM plugin / nam-juce, TONE3000 A2 API, JUCE, local-LLM options, current Anthropic model IDs,
   Supabase features) and reconcile. Where your current knowledge or search results improve on
   this brief, prefer the improvement — but honor the Prime Directives, and record every deviation
   in `docs/DECISIONS.md` (create it; see `08`).
3. **Scaffold the repo and git** (`09-GIT-AND-DELIVERY.md`): init, remote, `.gitignore`, structure,
   first commit.
4. **Build in phases** per `07-BUILD-ROADMAP.md` (Phase 0 → 3). Each phase ends in something that
   runs and is committed.
5. **Test** as you go (the brain has a real test suite; keep it green). Provide run/test
   instructions.
6. **Write the top-level `README.md`** and per-component docs (see `09` for required contents).
7. **Commit in logical units and push** to the remote. Leave the repo in a state the user can
   clone and run by following the README.

## What to build (high level)

- `brain/` — Python package: parse → retrieve → generate → validate(+repair) → write preset.
  Runnable end-to-end with a cloud LLM in Phase 1. This is the user's wheelhouse; make it solid.
- `plugin/` — JUCE Audio Unit forked from an existing open-source NAM plugin, extended with an
  internal effects chain and a patch loader. Heavier lift; spec is in `05-PLUGIN-SPEC.md`.
- `schema/` — the canonical `patch.schema.json` + `capture.manifest.schema.json` (in
  `docs/reference/`, copy them in and treat as the contract).
- `supabase/` — optional cloud home for capture metadata + recipe KB (migration + sync), behind
  the same retrieval interface as the local-file path.
- `docs/`, `examples/`, `recipes/` — as specified.

## Definition of done

- `git clone` + following the README gets the user a working brain that turns a request into a
  valid `patch.json` (Phase 1), and a build path for the AU plugin (Phase 2 spec, ideally a
  compiling baseline).
- Tests pass. Prime Directives upheld. `docs/DECISIONS.md` records any deviations and the
  research findings that motivated them.
- Everything pushed to `https://github.com/vivbandy/diy-guitar-pedal.git`.

## How to use `docs/reference/`

Those files are the **verbatim, known-good artifacts** from the design. Treat the two `*.schema.json`
files and `system_parse.md` as the canonical contract and prompt — copy them into the repo as-is
(you may extend, not silently break, them). The `*.example.*.json`, `recipes.seed.jsonl`,
`patch.gbnf`, `validate_reference.py`, and `supabase_schema.reference.sql` are correct reference
implementations you should reproduce/adapt. If your research turns up a better schema shape, evolve
it deliberately and note it in `DECISIONS.md`.
