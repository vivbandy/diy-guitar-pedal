# plugin — the real-time half (Audio Unit)

One AU instance = one complete patch. Insert it on a guitar track in Logic Pro or GarageBand,
point it at a `patch.json`, and hear the whole designed chain: amp capture → cab IR → effects.

**Status: partially built.** The framework-free core (patch spec, chain host, effect DSP,
file-watch transport) is written, compiles clean under `-Wall -Wextra`, and passes 107 checks.
The AU wrapper is **not** built — it needs the fork below plus `cmake`, which is not installed on
this machine. See [Getting to a running AU](#getting-to-a-running-au).

## Prime directives this half owns

- **Audio Unit only.** Logic and GarageBand load AU, not VST. VST3 builds are a side effect, not
  the target.
- **Temporal decoupling.** `processBlock` never parses JSON, never touches the filesystem, never
  allocates, never locks. Patches are parsed and chains are built on the message thread, then
  published to the audio thread with a single atomic pointer swap.

## Baseline: `sdatkinson/NeuralAmpModelerPlugin`

`docs/05-PLUGIN-SPEC.md` suggested `Tr3m/nam-juce`. Research on 2026-08-06 reversed that — see
`docs/DECISIONS.md`:

| | `sdatkinson/NeuralAmpModelerPlugin` | `Tr3m/nam-juce` |
|---|---|---|
| Last push | 2026-06-12 | **2024-10-08** |
| License | **MIT** | GPL-3.0 |
| Stars | 2,911 | 71 |
| Already ships | NAM loader, IR convolution, noise gate, tone stack | NAM loader |
| Framework | iPlug2 | JUCE 8 |

Both build an AU. The original is maintained, permissively licensed, and already has the IR
loader and two of the effects, so it is the faster path to a working AU. `nam-juce` being ~2 years
stale is the deciding factor.

`.nam` architecture **A2** needs NeuralAmpModelerCore ≥ v0.5.2; A1 models keep working. Check the
submodule pin after forking.

## What is in `src/`

The design constraint here: **the DSP and chain logic have no dependency on the plugin framework
or on a JSON library.** That is what lets the whole thing be tested with a compiler and nothing
else, and it keeps the fork's diff small.

```
src/
  PatchSpec.h/.cpp        plain-struct mirror of schema/patch.schema.json + version gating
  Manifest.h              capture_id -> local .nam/.wav path
  ChainHost.h/.cpp        builds the ordered chain (message thread), runs it (audio thread)
  effects/
    Effect.h              prepare() / setParams() / process() contract
    Biquad.h              RBJ cookbook biquad
    Effects.h/.cpp        Drive, Eq, Compressor, NoiseGate, Delay, Reverb, Modulation, Filter
  transport/
    FilePatchSource.h/.cpp   Phase 3: poll a path, reload on atomic replace

  PatchLoader.h/.cpp      JSON -> PatchSpec        <- the only two files needing nlohmann/json
  ManifestJson.cpp        JSON -> Manifest
```

`nam_capture` and `ir_cab` are deliberately **not** effects. `ChainHost::build` records them as
`CaptureSlot`s with their resolved local path and chain position; the fork's own NAM model host
and IR convolver render them. That is the seam where this code meets the baseline.

## Test the core now

No cmake, no JUCE, no fork required:

```bash
./plugin/tests/run.sh
```

Covers schema-version gating, manifest path resolution, chain ordering, disabled nodes, io gains,
the amp-head-without-a-cab warning, mono and stereo buffers, and numerical stability of every
effect (including a delay at 0.9 feedback).

With cmake available it is the same tests via `cmake -B build && cmake --build build && ctest --test-dir build`.

## Getting to a running AU

```bash
brew install cmake                      # not currently installed
gh repo fork sdatkinson/NeuralAmpModelerPlugin --clone --fork-name diy-guitar-pedal-au
```

1. **Build the fork unmodified first** and confirm it loads a `.nam` in Logic. Do not change
   anything before that works — you want a known-good starting point.
2. Add this directory's `src/` to the fork's build and set `TONE_WITH_JSON=ON` (iPlug2 already
   vendors nlohmann/json).
3. In the plugin's `OnReset`, call `ChainHost::prepare(sampleRate, blockSize)`.
4. Wire a "Load Patch…" file picker: `loadPatchFromFile` → `ChainHost::build` → `publish`. Surface
   `BuildResult::warnings` in the UI; refuse to publish when `error` is set.
5. In `ProcessBlock`, walk `Chain::positions` and `Chain::captures` together so the NAM model and
   IR convolver render at their recorded chain positions, with `ChainHost::process` running the
   effects around them.
6. Phase 3: hang `FilePatchSource::poll()` off a 250 ms message-thread timer so the brain's
   atomic writes reload live.

### Install

```bash
cmake --build build --config Release -j
cp -R build/**/Release/*.component ~/Library/Audio/Plug-Ins/Components/
killall -9 AudioComponentRegistrar   # force Logic to rescan
```

### Phase 2 done means

The AU is inserted in Logic, `examples/patch.example.gilmour.json` is loaded against a manifest
pointing at real files, and the full tone plays — fuzz → Hiwatt head → Greenback cab IR → delay →
reverb — with no dropouts.

## Licensing

This directory's own code is MIT (see the repo `LICENSE`). It is **not** standalone: it is
designed to be compiled into a fork of NeuralAmpModelerPlugin, which carries the licenses of NAM,
NeuralAmpModelerCore, and iPlug2. If you switch to a JUCE baseline, JUCE's licence has its own
distribution terms. Personal use is fine; **review every dependency's obligations before shipping
a binary to anyone else.**
