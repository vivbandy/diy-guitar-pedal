# docs — design record

These are the project's durable design documents. They started life as a build brief handed to
Claude Code; the project described in them has since been built, so read them as the *why* behind
the code rather than as instructions.

## Design docs

- `01-CONTEXT-AND-VISION.md` — the why + domain primer (NAM, IRs, amp-head vs full-rig, glossary).
- `02-ARCHITECTURE.md` — brain/plugin decoupling, the patch contract, data sources.
- `03-CONTRACTS.md` — the data model; the canonical schemas live in `../schema/`.
- `04-BRAIN-SPEC.md` — the Python pipeline.
- `05-PLUGIN-SPEC.md` — the Audio Unit plan. **Note:** its preference for `Tr3m/nam-juce` was
  overturned by research — see `DECISIONS.md`. The rest still holds.
- `06-SUPABASE-SPEC.md` — the optional cloud data source.
- `07-BUILD-ROADMAP.md` — phased tasks with exit criteria; the status table in the top-level
  README says where things actually stand.

## Decisions

- **`DECISIONS.md`** — every research finding and every deviation from the brief, with dates and
  sources. Start here if something in `01`–`07` doesn't match the code.

## Reference

- `reference/` — the verbatim canonical artifacts the contract was built from: the two JSON
  Schemas, the system prompt, both example patches, the example manifest, the GBNF grammar, the
  reference validator, the seed recipes, and the Supabase SQL. They have been copied into
  `../schema/`, `../examples/`, `../recipes/`, `../supabase/`, and `../brain/tone_architect/prompts/`;
  this folder is kept as the untouched original.

## Handoff

- `handoff/00-START-HERE.md` — the original runbook. **The six Prime Directives in it are still
  load-bearing** and every change should be checked against them.
- `handoff/08-RESEARCH-CHECKLIST.md` — the pre-build verification list. Worked through on
  2026-08-06; results in `DECISIONS.md`.
- `09-GIT-AND-DELIVERY.md` — repo layout, README requirements, commit plan.
