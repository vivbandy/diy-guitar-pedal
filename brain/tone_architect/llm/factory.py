from __future__ import annotations

import os

from ..config import Config
from .base import LLMClient


def make_llm(config: Config) -> LLMClient:
    if config.backend == "local":
        from .local import LocalLLM

        return LocalLLM(config, use_grammar=os.getenv("TONE_LOCAL_GRAMMAR") == "1")
    if config.backend == "cloud":
        from .cloud import CloudLLM

        return CloudLLM(config)
    raise ValueError(f"Unknown TONE_BACKEND {config.backend!r} (expected 'cloud' or 'local')")
