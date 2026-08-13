-- LLM Tone Architect — Supabase schema
-- Tables mirror schema/capture.manifest.schema.json and recipes/recipes.seed.jsonl.
-- Run via the Supabase SQL editor, the Supabase CLI, or psql.

-- Optional: enable pgvector now so you can add semantic search later without a migration.
create extension if not exists vector;

-- ─────────────────────────────────────────────────────────────────────────────
-- captures: the metadata catalog of your NAM/IR library.
-- The actual .nam/.wav files stay LOCAL on the machine running the plugin (the
-- audio engine needs fast local file access). This table holds metadata only;
-- `file` is the path relative to your local capture root.
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists captures (
    id          text primary key,
    name        text not null,
    file        text not null,
    format      text not null default 'nam'  check (format in ('nam','wav_ir')),
    category    text not null               check (category in ('amp','pedal','cab','outboard')),
    gain        text not null default 'n_a'  check (gain in ('clean','crunch','mid_gain','high_gain','fuzz','n_a')),
    includes_cab boolean not null default false,  -- amp captures: true = full rig (has cab), false = amp head (needs IR)
    character   text[] not null default '{}',
    tags        text[] not null default '{}',
    source      text,
    sample_rate integer,
    notes       text,
    -- Optional semantic-search column (1536 = OpenAI text-embedding-3-small; adjust to your model).
    embedding   vector(1536),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index if not exists captures_gain_idx     on captures (gain);
create index if not exists captures_category_idx on captures (category);
create index if not exists captures_tags_idx     on captures using gin (tags);
create index if not exists captures_char_idx      on captures using gin (character);

-- ─────────────────────────────────────────────────────────────────────────────
-- recipes: the curated tone knowledge base used to ground the model.
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists recipes (
    id           text primary key,
    name         text not null,
    artist       text,
    song         text,
    tags         text[] not null default '{}',
    description  text,
    chain_sketch text[] not null default '{}',
    embedding    vector(1536),
    created_at   timestamptz not null default now()
);

create index if not exists recipes_tags_idx on recipes using gin (tags);

-- ─────────────────────────────────────────────────────────────────────────────
-- OPTIONAL: pgvector RPCs for semantic retrieval. Wire these in behind
-- SupabaseLibrary.search() / SupabaseRecipeSource.lookup() once you compute
-- embeddings during sync. Until then the app uses keyword scoring (no embeddings needed).
-- ─────────────────────────────────────────────────────────────────────────────
create or replace function match_captures(query_embedding vector(1536), match_count int)
returns setof captures
language sql stable
as $$
    select * from captures
    where embedding is not null
    order by embedding <=> query_embedding
    limit match_count;
$$;

create or replace function match_recipes(query_embedding vector(1536), match_count int)
returns setof recipes
language sql stable
as $$
    select * from recipes
    where embedding is not null
    order by embedding <=> query_embedding
    limit match_count;
$$;
