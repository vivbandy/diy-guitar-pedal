"""Locate the canonical JSON Schema files.

`schema/` at the repo root is the single source of truth; the package deliberately does not
vendor a copy, so the two can never drift.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path


def schema_dir() -> Path | None:
    override = os.getenv("TONE_SCHEMA_DIR")
    if override:
        p = Path(override).expanduser()
        return p if p.is_dir() else None

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "schema" / "patch.schema.json"
        if candidate.is_file():
            return candidate.parent
    return None


@lru_cache(maxsize=8)
def load_json_schema(name: str) -> dict | None:
    d = schema_dir()
    if d is None:
        return None
    path = d / name
    if not path.is_file():
        return None
    return json.loads(path.read_text())
