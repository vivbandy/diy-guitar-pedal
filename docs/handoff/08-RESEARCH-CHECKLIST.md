# 08 · Research checklist — verify before you build

This brief was drafted from information current in **early 2026**. Before building, confirm the
ecosystem hasn't moved, and prefer current best practice where it improves on this design (without
breaking the Prime Directives). **Record findings and every deviation in `docs/DECISIONS.md`**
(create it — an ADR-style log: date, question, finding, decision, rationale).

Use your own up-to-date knowledge and web search where available. If you cannot verify an item,
proceed with the reference design and note the assumption.

## Confirm / update these

1. **Anthropic model id.** Do not hardcode a stale model. Confirm the current recommended model id
   for the cloud brain and set it in `config.py`. Verify the Messages API request shape you use is
   current.
2. **NAM plugin / AU baseline.** Check the current state of `sdatkinson/NeuralAmpModelerPlugin`,
   `Tr3m/nam-juce`, and any newer open-source NAM AU (including "shell"/"universal" hosts that
   already bundle NAM + IR + effects). Pick the baseline that gets a clean AU with `.nam` + IR
   loading fastest, with room to add an effects chain. Record the choice.
3. **NAM architecture (A2) & file format.** Confirm the current `.nam` format/version and that the
   chosen plugin/core supports it. Note any embedded-vs-plugin differences that matter.
4. **TONE3000 API.** Verify the current public API (auth flow, endpoints, the `amp` vs `full-rig`
   `gears` distinction, model-file URLs). Decide whether to add a `tone3000-sync` that populates the
   manifest / `captures` table and sets `includes_cab` directly (better than filename inference).
5. **JUCE.** Confirm the current JUCE version and its AU (and AUv3) build story on current macOS;
   update CMake accordingly.
6. **Local LLM path.** Confirm llama.cpp's current OpenAI-compatible server + grammar (GBNF)
   support, and whether a better small model now exists for constrained JSON / tool-style output.
   Keep grammar-constrained decoding unless something clearly better exists.
7. **Supabase.** Confirm current `supabase-py`, pgvector availability, and the recommended embedding
   approach if/when you wire semantic search. Keep the vector dimension consistent with the model.
8. **Speech-to-text (Phase 3, optional).** Confirm the current best local STT (e.g. whisper.cpp or
   successor) if adding voice input.

## Suggested searches

- "Neural Amp Modeler plugin Audio Unit open source 2026", "nam-juce fork AU effects chain"
- "TONE3000 API v1 gears amp full-rig endpoints", "TONE3000 A2 nam format"
- "JUCE Audio Unit build macOS 2026 CMake", "llama.cpp GBNF grammar server 2026"
- "best small local LLM structured JSON output 2026", "supabase pgvector embedding 2026"
- current Anthropic model ids / Messages API docs

## Decision points to resolve and log

- Which NAM AU to fork (and why).
- Whether to integrate the TONE3000 API now or defer (and how `includes_cab` is populated).
- Cloud model id + whether to also stand up the local backend in v1.
- Whether to keep the JSON-schema shape as-is or evolve it (justify any change).
- Embedding provider/dimension if enabling semantic retrieval.

The goal isn't to redesign — the Prime Directives and the contracts are stable. It's to make sure
the *implementations* (models, libraries, plugin baseline, APIs) are current on the day you build.
