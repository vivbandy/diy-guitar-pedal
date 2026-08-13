# 09 · Git & delivery

## Coordinates

- **Local working dir:** `~/src/diyguitarproject`
- **Remote:** `https://github.com/vivbandy/diy-guitar-pedal.git`

Work inside `~/src/diyguitarproject`. The docs you're reading live in that directory's `docs/`
folder — keep them (they're the project's design record). You may move the pure-handoff files
(`00-START-HERE`, `08-RESEARCH-CHECKLIST`) into `docs/handoff/` if you prefer, but keep the durable
design docs (`01`–`07`) in `docs/`.

## Repo setup

```bash
cd ~/src/diyguitarproject
git init            # if not already a repo
git remote add origin https://github.com/vivbandy/diy-guitar-pedal.git 2>/dev/null || \
  git remote set-url origin https://github.com/vivbandy/diy-guitar-pedal.git
git fetch origin || true
# If the remote already has commits (e.g. an initial README/license), reconcile first:
git pull --rebase origin main 2>/dev/null || git pull --rebase origin master 2>/dev/null || true
```

Use the remote's default branch (`main` unless it's `master`). Don't force-push over existing
history; rebase/merge instead.

## Recommended final repo structure

```
diy-guitar-pedal/
  README.md                 # top-level: what it is, quickstart, architecture summary, status
  LICENSE                   # MIT for own code (+ note NAM/JUCE deps carry their own licenses)
  Makefile                  # install/test/lint/generate/validate/scaffold/db-sync/clean
  .gitignore                # python, build artifacts, *.nam, captures/, plugin/build/, .env
  docs/                     # these design docs + DECISIONS.md + reference/
  schema/                   # patch.schema.json, capture.manifest.schema.json
  brain/                    # the Python package + tests (see 04)
  plugin/                   # JUCE AU: SPEC + source as it lands (see 05)
  supabase/                 # migrations + README (see 06)
  examples/                 # example manifest + example patches
  recipes/                  # recipes.seed.jsonl + README
```

## .gitignore essentials

```
__pycache__/  *.egg-info/  .venv/  build/  dist/  .pytest_cache/  .ruff_cache/
brain/out/  out/  *.nam  captures/  plugin/build/  *.component  *.vst3  .env  .DS_Store
```

Never commit capture binaries (`*.nam`/large `.wav`) or secrets (`.env`, Supabase keys).

## README.md — required contents (top level)

1. One-paragraph what/why + the "describe a tone → playable patch in Logic/GarageBand" pitch.
2. Architecture summary (the brain/plugin decoupling + the patch contract) with a pointer to
   `docs/02-ARCHITECTURE.md`.
3. **Quickstart (brain):** create venv, `make install-dev`, set `ANTHROPIC_API_KEY`, scaffold a
   manifest from a captures folder, generate a patch, validate it. Copy/paste-able commands.
4. **How to test:** `make test` (and what the tests cover, including cabinet pairing).
5. **Capture library:** how to build the manifest, the amp-head vs full-rig / `includes_cab` rule,
   and that `.nam` files stay local.
6. **Supabase (optional):** apply the migration, set env, `make db-sync`.
7. **Plugin:** current status + build/install steps (`05-PLUGIN-SPEC.md`) and the AU-only note.
8. **Roadmap + status:** which phases are done; link `docs/07-BUILD-ROADMAP.md`.
9. **Licensing note** for NAM/JUCE dependencies.

Also write `brain/README.md`, `supabase/README.md`, `recipes/README.md`, and `plugin/README.md`
as described in their specs.

## Commit plan (logical units, not one giant commit)

Suggested sequence:
1. `chore: repo skeleton, docs, .gitignore, license`
2. `feat(schema): patch + capture manifest contracts + examples`
3. `feat(brain): models + validation (incl. cabinet pairing) + tests` (Phase 0)
4. `feat(brain): retrieval + LLM backends + pipeline + CLI` (Phase 1)
5. `feat(brain): scaffolder`
6. `feat(supabase): migration + sync + supabase-backed retrieval`
7. `docs: top-level README + component READMEs`
8. `feat(plugin): AU baseline + spec` (Phase 2 start), then chain/effects/loader commits
9. `chore: DECISIONS.md with research findings`

Write clear commit messages. Keep the working tree green (tests passing) at each brain commit.

## Push

```bash
git add -A
git commit -m "…"          # per the plan above
git push -u origin main    # or master, matching the remote default
```

If auth is needed, use the user's configured GitHub credentials/token (don't hardcode secrets).
Confirm the push succeeded and the tree on GitHub matches local.

## Hand back to the user

When done, summarize for the user: what was built, what's runnable now (with the exact commands),
what's stubbed/spec-only (the plugin phases), key decisions logged in `DECISIONS.md`, and the next
step they'd take. Keep it concrete.
