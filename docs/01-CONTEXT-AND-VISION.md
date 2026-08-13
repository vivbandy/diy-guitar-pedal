# 01 · Context & vision

## What the user wants

A personal, hobby tool. The user plays guitar and records in Logic Pro / GarageBand on a Mac.
They want to *describe* a tone in natural language and have software assemble a complete, playable
guitar rig for them from freely available neural captures — instead of manually hunting for amps,
matching cabinets, and dialing effects. Example request:

> "Create a patch that sounds like David Gilmour's lead from Comfortably Numb."

The system should pick the right amp capture, pair it with a cabinet, add the right pedals/effects
in the right order with sensible settings, and hand back something they can immediately play
through while recording.

## How we arrived at this design (the reasoning worth preserving)

The idea started as a hardware pedal but converged on a **software plugin** for good reasons:

- **Latency.** A DIY Raspberry Pi audio path is ~15 ms round-trip (playable but not transparent);
  a bare-metal microcontroller (Daisy Seed) is ~1–5 ms but demands C++ firmware and soldering. A
  plugin inside the user's existing DAW inherits the DAW + audio-interface latency handling for
  free. (Hardware remains a possible future direction, not the current target.)
- **Two workloads, opposite needs.** Understanding language (LLM) is heavy and bursty but
  latency-tolerant; processing audio is light but hard-real-time. They **never run at the same
  time** — you're not playing while asking for a tone. So they should be *decoupled*: the LLM
  emits a patch file; the audio plugin loads it. This is the core architectural insight.
- **The model's job is selection, not omniscience.** It doesn't invent amps; it assembles a chain
  from the user's downloaded captures, grounded by a small curated "recipe" knowledge base and the
  user's capture library metadata. This keeps quality high even with smaller/local models.

See `02-ARCHITECTURE.md` for the full design.

## Domain primer (you must internalize this — it drives correctness rules)

**NAM (Neural Amp Modeler)** — free, open-source tech that captures the sound/feel of real amps
and pedals into small `.nam` files. Sourced primarily from **TONE3000** (the largest NAM library).
The current NAM architecture generation is "A2". Captures come in types:

- **Amp head** — amplifier ONLY, no speaker cabinet. On its own it sounds thin and harsh ("a swarm
  of fizzy bees"). **It must be paired with a cabinet IR.**
- **Full rig / combo** — amp + cab captured together. Ready to use; adding a separate cab IR
  double-cabs it and sounds over-filtered.
- **Pedal** — overdrive/distortion/fuzz/etc. Placed BEFORE the amp.
- **Outboard** — studio gear (compressor/EQ). Usually placed at the end.

**IR (Impulse Response)** — a small `.wav` that models a speaker cabinet (+ mic + room). Convolved
with the signal. The cab IR is roughly **half** the final tone. In our data model it's an `ir_cab`
node referencing a `cab`-category capture.

**The cabinet-pairing rule (a correctness requirement, not a preference):**
- amp-head capture present ⇒ the patch MUST contain a cab IR after it (else: thin tone).
- full-rig capture present ⇒ the patch MUST NOT add a cab IR (else: double-cab).
Captures therefore carry an `includes_cab` boolean. Validation enforces this rule; the repair loop
lets the model self-correct. This directly prevents the most common beginner mistake.

**Typical signal-chain order:** dynamics/filter → drive/fuzz (pedals) → amp core → cab IR (only if
amp head) → post EQ → delay → reverb → modulation.

**Plugin format:** Logic Pro and GarageBand load **Audio Units (AU)** only — not VST. The NAM
ecosystem already has open-source AU plugins that load `.nam` captures and have an IR loader; we
fork one and add an effects chain. (See `05-PLUGIN-SPEC.md`.)

## Glossary

- **Capture / NAM model** — neural snapshot of an amp/pedal (`.nam`). Fixed; you select one, you
  don't turn its knobs.
- **Amp head / full rig** — see above; the `includes_cab` distinction.
- **IR / cab IR** — speaker-cab impulse response (`.wav`); the `ir_cab` node.
- **Tone core** — the amp (+ cab) that gives a patch its fundamental voice. Every patch needs one.
- **Patch** — a complete loadable tone: an ordered chain of an amp core plus effects. The unit of
  exchange between brain and plugin (`patch.json`).
- **Manifest** — the catalog of the user's captures (metadata + tags + `includes_cab`). The model
  can only choose from what's in here.
- **Recipe** — a curated, human-readable sketch of a known real-world tone's signal chain, used to
  ground the model.
- **Brain** — the Python pipeline (request → patch). **Plugin** — the JUCE AU (patch → sound).

## Constraints & preferences

- Target macOS + AU. Python 3.11+ for the brain; JUCE/C++ for the plugin.
- The user uses **Supabase** — capture metadata and the recipe KB can live there (pgvector-ready),
  but the actual `.nam`/`.wav` binaries stay on local disk (the audio engine needs fast local
  access). Supabase is opt-in behind the same retrieval interface as local JSON.
- Keep it approachable: the brain should run end-to-end early so the user sees value fast.
