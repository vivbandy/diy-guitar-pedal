from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Text in, JSON out. Backends differ only in how they constrain the output.

    `schema` defaults to the patch schema; discovery passes its own small schema for the gear plan.
    """

    name: str

    def complete(self, system: str, user: str, schema: dict[str, Any] | None = None) -> str: ...
