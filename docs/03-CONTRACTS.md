# 03 · Contracts (the data model)

These are the interfaces both halves are built around. **Copy the canonical files from
`docs/reference/` into the repo** (suggested: `schema/`) and treat them as the source of truth.
You may extend them; do not silently break them. Any change ripples to both the brain
(`models.py`) and the plugin (patch loader), so keep them in lockstep and add a test asserting the
pydantic models and the JSON schema agree.

## Files (in `docs/reference/`)

- `patch.schema.json` — the patch: an ordered `chain` of typed nodes + `io` gains + metadata.
  Node types: `nam_capture`, `ir_cab`, `drive` (boost/overdrive/distortion/fuzz via `style`),
  `compressor`, `noise_gate`, `eq` (parametric bands + shelves), `delay`, `reverb`, `modulation`
  (chorus/flanger/phaser/tremolo via `style`), `filter` (lp/hp/bp/wah). Uses draft 2020-12,
  discriminated on `type` via `oneOf` + `$defs`.
- `capture.manifest.schema.json` — the user's library catalog. Each capture has `id`, `name`,
  `file`, `format` (`nam`|`wav_ir`), `category` (`amp`|`pedal`|`cab`|`outboard`), `gain`,
  **`includes_cab`** (amp head vs full rig), `character[]`, `tags[]`.
- `patch.example.gilmour.json` — amp-HEAD capture + required cab IR (demonstrates pairing).
- `patch.example.srv.json` — FULL-RIG capture, no cab IR (demonstrates the other branch).
- `captures.manifest.example.json` — example library with both amp-head and full-rig captures and
  two cab IRs; the examples reference these ids.

## Invariants the contract encodes

1. Every `nam_capture`/`ir_cab` `capture_id` must exist in the manifest.
2. A valid patch has at least one tone core (`nam_capture` or `ir_cab`).
3. Cabinet pairing (enforced by the validator, not just the schema):
   - amp-head `nam_capture` present ⇒ an `ir_cab` must follow it.
   - full-rig `nam_capture` present ⇒ no `ir_cab` (warn if present).
4. Parameters stay within documented ranges; the plugin clamps defensively.

## Mirroring in code

- Python: a `models.py` with pydantic v2 models mirroring the schema (a discriminated union of node
  types on `type`; a `Capture`/`CaptureManifest` pair with `ids()`/`by_id()`; a `Patch` with a
  `capture_ids()` helper). Keep field names identical to the JSON schema.
- Plugin: a parser that maps each node to a DSP block and resolves `capture_id` → local file via
  the manifest.

## Versioning

`schema_version` is currently `"1.0"`. Bump it if you make a breaking change, and have the plugin
reject unknown major versions rather than mis-parse.
