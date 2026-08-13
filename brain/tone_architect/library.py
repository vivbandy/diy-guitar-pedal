"""Capture library behind an interface, so the file manifest and Supabase are interchangeable."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from .config import Config
from .models import Capture, CaptureManifest
from .retrieval.captures import score_captures
from .validate import load_manifest


@runtime_checkable
class CaptureLibrary(Protocol):
    def ids(self) -> set[str]: ...

    def by_id(self, capture_id: str) -> Capture | None: ...

    def search(self, request: str, limit: int = 24) -> list[Capture]: ...


class ManifestLibrary:
    """File-backed library: a capture manifest JSON on disk."""

    def __init__(self, manifest: CaptureManifest, root: Path | None = None):
        self.manifest = manifest
        self.root = root
        self._by_id = {c.id: c for c in manifest.captures}

    @classmethod
    def from_path(cls, path: str | Path) -> ManifestLibrary:
        p = Path(path).expanduser()
        return cls(load_manifest(p), root=p.parent)

    def ids(self) -> set[str]:
        return set(self._by_id)

    def by_id(self, capture_id: str) -> Capture | None:
        return self._by_id.get(capture_id)

    def all(self) -> list[Capture]:
        return list(self.manifest.captures)

    def search(self, request: str, limit: int = 24) -> list[Capture]:
        return score_captures(self.all(), request, limit=limit)

    def resolve_file(self, capture_id: str) -> Path | None:
        cap = self.by_id(capture_id)
        if cap is None:
            return None
        base = Path(self.manifest.root) if self.manifest.root else Path(".")
        if not base.is_absolute() and self.root is not None:
            base = self.root / base
        return base / cap.file


class SupabaseLibrary:
    """Supabase-backed library.

    Reuses the same scorer as the file path — one ranking, two sources.
    """

    def __init__(self, url: str, key: str, table: str = "captures"):
        from supabase import create_client

        self._client = create_client(url, key)
        self._table = table
        self._cache: list[Capture] | None = None

    def all(self) -> list[Capture]:
        if self._cache is None:
            rows = self._client.table(self._table).select("*").execute().data or []
            self._cache = [Capture.model_validate(_clean_row(r)) for r in rows]
        return self._cache

    def ids(self) -> set[str]:
        return {c.id for c in self.all()}

    def by_id(self, capture_id: str) -> Capture | None:
        for c in self.all():
            if c.id == capture_id:
                return c
        return None

    def search(self, request: str, limit: int = 24) -> list[Capture]:
        return score_captures(self.all(), request, limit=limit)


def _clean_row(row: dict) -> dict:
    allowed = set(Capture.model_fields)
    out = {k: v for k, v in row.items() if k in allowed and v is not None}
    out.setdefault("character", [])
    out.setdefault("tags", [])
    return out


def make_library(config: Config, manifest_path: str | Path | None = None) -> CaptureLibrary:
    if config.source == "supabase":
        if not (config.supabase_url and config.supabase_key):
            raise RuntimeError("TONE_SOURCE=supabase requires SUPABASE_URL and SUPABASE_KEY")
        return SupabaseLibrary(config.supabase_url, config.supabase_key)
    if manifest_path is None:
        raise RuntimeError("TONE_SOURCE=file requires a manifest path (--manifest)")
    return ManifestLibrary.from_path(manifest_path)
