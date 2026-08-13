"""Environment-driven configuration.

Nothing here holds a secret at rest: API keys are read from the environment on demand and never
written to disk or logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Verified 2026-08-06 against the current Anthropic model list. Override with TONE_CLOUD_MODEL
# rather than editing this — the point is to not carry a stale id.
DEFAULT_CLOUD_MODEL = "claude-opus-5"
DEFAULT_LOCAL_MODEL = "qwen3-8b-instruct"
DEFAULT_LOCAL_URL = "http://127.0.0.1:8080/v1"


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    backend: str = "cloud"
    cloud_model: str = DEFAULT_CLOUD_MODEL
    cloud_effort: str = "medium"
    cloud_max_tokens: int = 8000
    local_url: str = DEFAULT_LOCAL_URL
    local_model: str = DEFAULT_LOCAL_MODEL
    source: str = "file"
    supabase_url: str | None = None
    supabase_key: str | None = None
    tone3000_token: str | None = None
    max_repair_attempts: int = 2
    max_candidates: int = 24
    max_recipes: int = 3

    @classmethod
    def load(cls) -> Config:
        return cls(
            backend=os.getenv("TONE_BACKEND", "cloud").strip().lower(),
            cloud_model=os.getenv("TONE_CLOUD_MODEL", DEFAULT_CLOUD_MODEL).strip(),
            cloud_effort=os.getenv("TONE_CLOUD_EFFORT", "medium").strip().lower(),
            cloud_max_tokens=_int("TONE_CLOUD_MAX_TOKENS", 8000),
            local_url=os.getenv("TONE_LOCAL_URL", DEFAULT_LOCAL_URL).strip(),
            local_model=os.getenv("TONE_LOCAL_MODEL", DEFAULT_LOCAL_MODEL).strip(),
            source=os.getenv("TONE_SOURCE", "file").strip().lower(),
            supabase_url=os.getenv("SUPABASE_URL") or None,
            supabase_key=os.getenv("SUPABASE_KEY") or None,
            tone3000_token=os.getenv("TONE3000_TOKEN") or None,
            max_repair_attempts=_int("TONE_MAX_REPAIR_ATTEMPTS", 2),
            max_candidates=_int("TONE_MAX_CANDIDATES", 24),
            max_recipes=_int("TONE_MAX_RECIPES", 3),
        )
