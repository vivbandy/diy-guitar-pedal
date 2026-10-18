# LLM Tone Architect

**Describe a guitar tone in plain English; get a playable patch in Logic Pro or GarageBand.**

Ask for *"David Gilmour's sustaining lead from Comfortably Numb"* and the system assembles a
complete signal chain out of **your own** capture library — a Big Muff-ish fuzz, the Hiwatt head
you captured, a Greenback 4x12 IR after it, a 460 ms analog delay, a touch of hall — writes it as
a validated `patch.json`, and an Audio Unit loads it. The model picks from what you actually own;
it never invents an amp you don't have, and it never leaves an amp head without a cabinet.

## Architecture

Two halves that never share a thread, joined by one contract.

```
  "gilmour lead"
        │
        ▼
┌──────────────────────┐   patch.json    ┌─────────────────────┐
│ brain/  (Python)     │ ──────────────▶ │ plugin/  (Audio Unit)│ ──▶ 🔊
│ parse → retrieve →   │  validated,     │ loads the chain,     │
│ generate → validate  │  atomic write   │ renders in real time │
│ (+repair) → write    │                 │                      │
└──────────────────────┘                 └─────────────────────┘
   slow, thinks, cloud                      fast, dumb, real-time
```

The LLM is slow and occasionally wrong; the audio thread can tolerate neither. So the brain runs
entirely offline from audio and its only output is a `patch.json` that has already passed
validation. Patches reference captures by `capture_id`, never by file path — the plugin's manifest
owns that binding.

Details: [`docs/02-ARCHITECTURE.md`](docs/02-ARCHITECTURE.md). The contract itself lives in
[`schema/`](schema/).

## Quickstart (brain)

```bash
git clone https://github.com/vivbandy/diy-guitar-pedal.git
cd diy-guitar-pedal

make install-dev                        # creates .venv, installs the brain + dev tools
export ANTHROPIC_API_KEY=...            # or: ant auth login

# 1. Build a manifest of your captures (edit the `includes_cab` flags it guesses!)
make scaffold CAPTURES=~/Music/NAM

# 2. Generate a patch
.venv/bin/tone-architect "David Gilmour's sustaining lead from Comfortably Numb" \
    --manifest captures.manifest.json \
    --out out/gilmour.json

# 3. Check it
.venv/bin/tone-architect validate out/gilmour.json -m captures.manifest.json --strict
```

Want to try it before you have any captures? Everything works against the shipped example
library:

```bash
make generate REQUEST="warm clean strat, lots of headroom"
make validate-examples
```

Needs Python 3.11+ (3.13 recommended). Configuration is all environment variables — see
[`.env.example`](.env.example). `TONE_BACKEND=local` swaps the cloud model for a local
`llama-server` with no other changes.

## How to test

```bash
make test          # brain: 60 tests
make lint          # ruff check + format check
make plugin-test   # plugin core: 107 checks, compiled with clang++ (no cmake needed)
```

The brain suite covers the schema ↔ pydantic-model agreement, capture-existence rejection,
out-of-range parameters, malformed JSON, the bounded repair loop, and **all four cabinet-pairing
cases** — amp-head with and without a cab IR, full-rig with and without. That last group is the
point of the whole validator; see below.

## Capture library

Your `.nam` and `.wav` files **stay on your machine**. Nothing in this repo uploads them, and
`.gitignore` refuses to commit them. What travels is metadata: id, name, category, tags, and the
one flag that matters most.

```bash
make scaffold CAPTURES=~/Music/NAM     # infers from filenames — then edit by hand
```

### The `includes_cab` rule

A NAM capture of an **amp head** contains no speaker cabinet. Played on its own it sounds thin and
harsh — a guitar amp's tone is roughly half speaker. A capture of a **full rig** (a combo, or a
head miked through its cab) already includes one.

| Capture | `includes_cab` | Patch must… |
|---|---|---|
| Amp head | `false` | **add** an `ir_cab` node |
| Full rig / combo | `true` | **not** add one (double-cabbing sounds over-filtered) |

`validate.py` enforces the first as an error and flags the second as a warning, so a wrong tone
can't reach the plugin. Getting the flag wrong in your manifest defeats it — which is why
`tone3000-sync` is worth using:

```bash
export TONE3000_CLIENT_ID=...   # your TONE3000 *publishable* key
make t3k-login                  # approve a short code in the browser, once
make t3k-sync                   # reads your favorited tones
```

Favorites are per-user, so the sync needs you signed in; the secret key (`TONE3000_TOKEN`)
identifies the app, not you, and only works for `tone3000-sync --scope search`. The sign-in is
stored in `~/.config/tone-architect/tone3000.json` and refreshes itself.

TONE3000 records the distinction authoritatively as the tone's `gear` (`amp` vs `amp-cab`), so
syncing from the API sets `includes_cab` from real data instead of a filename guess.

### Discovery: let it find the gear

Don't have a library yet? `--discover` turns the request into a short gear list, searches
TONE3000 for each item, and builds the patch from what it finds:

```bash
.venv/bin/tone-architect "Gilmour's Comfortably Numb lead" --discover -m captures.manifest.json
# or: make discover REQUEST="..."
```

`includes_cab` still comes from TONE3000's `gear` field, so the cabinet rule holds. Only the
captures the patch actually uses are added to your manifest; add `--download` to fetch their model
files too. Each request costs one LLM call for the gear list plus one search per item (at most
six), since TONE3000 rate-limits search heavily. Your own captures stay in the running alongside
what it finds.

## Supabase (optional)

Metadata in the cloud, binaries still local. Off by default.

```bash
psql "$DATABASE_URL" -f supabase/migrations/0001_init.sql   # or paste into the SQL editor
export SUPABASE_URL=... SUPABASE_KEY=... TONE_SOURCE=supabase
make db-sync
```

The Supabase and file-backed libraries run the *same* Python scorer, so retrieval behaves
identically either way. See [`supabase/README.md`](supabase/README.md).

## Plugin

**Partially built.** The framework-free core — patch parsing, chain building, the effect DSP,
the file-watch transport — is written and passes 107 checks under `-Wall -Wextra`. The Audio Unit
wrapper is not: it needs a fork of
[`sdatkinson/NeuralAmpModelerPlugin`](https://github.com/sdatkinson/NeuralAmpModelerPlugin) and
`cmake`, which isn't installed here.

**Audio Unit only.** Logic Pro and GarageBand do not load VST. Full fork-and-build instructions
are in [`plugin/README.md`](plugin/README.md).

## Roadmap + status

| Phase | Scope | Status |
|---|---|---|
| 0 | Contract, models, validation, tests | ✅ done |
| 1 | Retrieval, LLM backends, pipeline, CLI, scaffolder, Supabase, TONE3000 | ✅ done (cloud path not run end-to-end — no API key on the build machine) |
| 2 | Audio Unit plugin | 🟡 core written + tested; AU wrapper not built |
| 3 | Live file-watch loop, voice input | ⚪ `FilePatchSource` written; not wired |

Full plan: [`docs/07-BUILD-ROADMAP.md`](docs/07-BUILD-ROADMAP.md). Every research finding and
deviation from the original brief is logged in [`docs/DECISIONS.md`](docs/DECISIONS.md).

## Licensing

This repository's own code is MIT ([`LICENSE`](LICENSE)). It depends on components that are not:
Neural Amp Modeler and NeuralAmpModelerCore, iPlug2 (or JUCE if you swap the plugin baseline), and
whatever license attaches to captures you download from TONE3000. Personal use is fine. **Review
each dependency's obligations before distributing a binary.**
