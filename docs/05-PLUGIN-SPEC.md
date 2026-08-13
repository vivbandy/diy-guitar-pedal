# 05 · Plugin spec (JUCE Audio Unit)

The real-time half: an Audio Unit that loads a `patch.json` and renders the tone in Logic Pro /
GarageBand. Heavier lift than the brain — spec it carefully, and get a compiling baseline before
adding DSP.

## Goal

One AU instance = one complete patch. Insert on a guitar track, load a `patch.json`, hear the full
designed tone (amp core + cab IR + effects).

## Why one self-contained plugin

A plugin cannot instantiate other plugins inside the DAW (host sandbox). So the effects chain lives
**inside** this one plugin. This also gives full programmatic control of the whole chain from a
single JSON file.

## Starting point — verify current best baseline first (see 08-RESEARCH-CHECKLIST)

The design assumes forking an open-source NAM AU that already loads `.nam` captures and has an IR
loader. As of early 2026 the candidates were:
- **`Tr3m/nam-juce`** — a JUCE port (preferred for the cleanest AU build + room to add DSP).
- `sdatkinson/NeuralAmpModelerPlugin` — the original (iPlug2), also builds AU.
- Evaluate any newer/better option your research surfaces (e.g. shell plugins that already host
  NAM + IR + effects, such as community "universal" NAM hosts). If a stronger baseline now exists,
  prefer it and record why in `DECISIONS.md`. **Confirm the fork builds a clean AU that loads a
  `.nam` in Logic before modifying anything.**

## What to add

```
plugin/
  src/
    PatchLoader.{h,cpp}      # parse patch.json -> chain spec; resolve capture_id via manifest
    ChainHost.{h,cpp}        # owns ordered nodes; runs them in processBlock
    Manifest.{h,cpp}         # load capture manifest; capture_id -> local .nam/.wav path
    effects/
      Effect.h               # base: prepare(), process(buffer), setParams(json)
      Drive, Compressor, NoiseGate, Eq, Delay, Reverb, Modulation, Filter (.{h,cpp})
    transport/
      FilePatchSource.{h,cpp}  # Phase 3: watch a path, reload on atomic replace
      OscPatchSource.{h,cpp}   # Phase 3 optional: receive patches over OSC/socket
```

`nam_capture` and `ir_cab` reuse the fork's existing NAM loader and IR convolution loader. The cab
IR (`ir_cab`) is a `.wav` run through convolution — the forked plugin already ships this.

## Real-time rules (non-negotiable)

- `processBlock` is lock-free and allocation-free: no JSON, no file IO, no `new`/`malloc`.
- Patch loading is on the message thread: parse → build the full new chain → atomic pointer swap
  for the audio thread to pick up. Reuse the fork's existing off-thread NAM model-load pattern and
  extend it to effects.
- Load-time parameter configuration only in v1 (no per-sample automation from the brain yet).

## Mapping a patch to the chain

1. Parse `patch.json` (reject unknown `schema_version` major).
2. For each `chain` node in order: `nam_capture`/`ir_cab` → resolve `capture_id` → local file →
   load; effects → instantiate the matching `Effect`, `setParams(node.params)`.
3. Assemble the ordered `ChainHost`; apply `io` gains at the boundaries; atomic swap.
4. Cabinet expectation: an amp-head `nam_capture` should be followed by an `ir_cab` (the brain
   guarantees this). Don't crash if a cab is missing — it just won't sound right; surface a warning.

## Effect implementation priority (Phase 2)

drive → eq → compressor → delay → reverb → modulation → noise_gate → filter. Each is standard DSP
with abundant open JUCE references; keep each behind the `Effect` interface.

## Transports

Phase 2: "Load Patch…" file picker (manual). Phase 3: watch a known path (brain writes there
atomically) and/or OSC for instant live push from a UI.

## Build & install (document in README)

```
cmake -B build
cmake --build build --config Release -j
cp -R build/.../Release/<Name>.component ~/Library/Audio/Plug-Ins/Components/
# rescan/restart Logic, insert on a guitar track
```

## Definition of done (Phase 2)

Insert the AU in Logic, load `docs/reference/patch.example.gilmour.json` (with a manifest pointing
at real `.nam`/`.wav` files), and the full tone plays — fuzz → amp head → cab IR → delay → reverb —
with no dropouts.

## Licensing

The plugin depends on NAM components and JUCE, each with its own license. For personal use this is
fine; **review obligations before distributing any binary** (JUCE especially). Note this in the
README.
