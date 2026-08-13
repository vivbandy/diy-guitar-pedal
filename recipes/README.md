# recipes — the tone knowledge base

Grounding for the model. A request like *"Comfortably Numb lead"* matches a recipe, and the
recipe's chain sketch goes into the prompt as structural guidance: which effect types, in roughly
what order, with what character.

Recipes describe **structure, not gear**. They never name a capture — capture choice is always
bound to what is actually in your library, which is the whole point of the `AVAILABLE CAPTURES`
list. A recipe saying "clean amp" lets the retriever offer whichever clean amp you own.

## Format

One JSON object per line (`recipes.seed.jsonl`):

```json
{"name":"Gilmour Comfortably Numb lead","artist":"David Gilmour","song":"Comfortably Numb","tags":["lead","fuzz","pink floyd","sustaining"],"description":"Big Muff fuzz into a clean high-headroom British amp, long ~quarter-note analog delay, light hall reverb, compression for sustain.","chain_sketch":["compressor","fuzz","clean amp","mild eq mid push","delay 440-480ms","hall reverb"]}
```

| Field | Notes |
|---|---|
| `name` | required |
| `artist`, `song` | optional, but they carry the most scoring weight — an exact artist or song match scores 6.0 |
| `tags` | genre and character words the request might use |
| `description` | one or two sentences; goes into the prompt verbatim |
| `chain_sketch` | freeform stage strings in signal order |

22 seeded recipes ship here.

## Adding your own

Append a line. That's it — `FileRecipeSource` reads the file on every run, and
`tone-sync --recipes` pushes them to Supabase with a stable derived `id`.

The scorer (`brain/tone_architect/retrieval/recipes.py`) only returns recipes that score above
zero, so a request with no match simply gets no hints rather than a misleading one. Up to
`TONE_MAX_RECIPES` (default 3) reach the prompt.
