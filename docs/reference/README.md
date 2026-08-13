# reference/ — canonical artifacts (verbatim)

These are the known-good, load-bearing artifacts from the design. Treat them as ground truth for
the contract; reproduce/adapt the rest per the specs. You may extend, not silently break, them.

- `patch.schema.json` — THE patch contract (ordered chain of typed nodes). Copy into `schema/`.
- `capture.manifest.schema.json` — the capture library catalog schema (incl. `includes_cab`).
- `system_parse.md` — the canonical LLM system prompt (teaches capture-only selection, the
  amp-head/full-rig cabinet rule, chain order, JSON-only output).
- `patch.gbnf` — GBNF grammar to force valid patch JSON from small local models (llama.cpp).
- `captures.manifest.example.json` — example library with amp-head + full-rig captures and cab IRs.
- `patch.example.gilmour.json` — amp-HEAD + required cab IR (demonstrates pairing).
- `patch.example.srv.json` — FULL-RIG, no cab IR (the other branch).
- `recipes.seed.jsonl` — 22 curated tone recipes across genres (grounding KB).
- `validate_reference.py` — the exact validation logic to reproduce (schema + capture existence +
  cabinet pairing + tone core; repair-friendly errors; warnings).
- `supabase_schema.reference.sql` — the Supabase migration (captures + recipes + pgvector RPCs).
