"""Recipe knowledge base behind an interface: JSONL file or Supabase, same scorer either way."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from .config import Config
from .retrieval.recipes import score_rows


@runtime_checkable
class RecipeSource(Protocol):
    def lookup(self, request: str, limit: int = 3) -> list[dict]: ...


class NullRecipeSource:
    def lookup(self, request: str, limit: int = 3) -> list[dict]:
        return []


class FileRecipeSource:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    @classmethod
    def from_path(cls, path: str | Path) -> FileRecipeSource:
        p = Path(path).expanduser()
        rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
        return cls(rows)

    def lookup(self, request: str, limit: int = 3) -> list[dict]:
        return score_rows(self.rows, request, limit=limit)


class SupabaseRecipeSource:
    def __init__(self, url: str, key: str, table: str = "recipes"):
        from supabase import create_client

        self._client = create_client(url, key)
        self._table = table
        self._cache: list[dict] | None = None

    def _all(self) -> list[dict]:
        if self._cache is None:
            self._cache = self._client.table(self._table).select("*").execute().data or []
        return self._cache

    def lookup(self, request: str, limit: int = 3) -> list[dict]:
        return score_rows(self._all(), request, limit=limit)


def make_recipe_source(config: Config, recipes_path: str | Path | None = None) -> RecipeSource:
    if config.source == "supabase" and config.supabase_url and config.supabase_key:
        return SupabaseRecipeSource(config.supabase_url, config.supabase_key)
    if recipes_path and Path(recipes_path).expanduser().is_file():
        return FileRecipeSource.from_path(recipes_path)
    return NullRecipeSource()


def default_recipes_path() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "recipes" / "recipes.seed.jsonl"
        if candidate.is_file():
            return candidate
    return None
