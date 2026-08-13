from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Text in, patch JSON out. Backends differ only in how they constrain the output."""

    name: str

    def complete(self, system: str, user: str) -> str: ...
