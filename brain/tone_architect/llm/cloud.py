"""Anthropic cloud backend.

Structured outputs pin the *shape* of the patch (node types, required fields, enums) but the API
strips numeric constraints such as `minimum`/`maximum`, so ranges are still only enforced by
validate.py. That is why the generate -> validate -> repair loop stays load-bearing.
"""

from __future__ import annotations

from typing import Any

from ..config import Config
from ..models import Patch

_UNSUPPORTED_KEYWORDS = frozenset(
    {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
        "uniqueItems",
        "default",
        "discriminator",
    }
)


def structured_output_schema() -> dict[str, Any]:
    """The Patch schema reduced to the subset the structured-outputs API accepts."""
    return _sanitize(Patch.model_json_schema())


def _sanitize(node: Any) -> Any:
    if isinstance(node, list):
        return [_sanitize(n) for n in node]
    if not isinstance(node, dict):
        return node

    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _UNSUPPORTED_KEYWORDS:
            continue
        if key == "oneOf":
            out["anyOf"] = _sanitize(value)
            continue
        out[key] = _sanitize(value)

    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
    return out


class CloudLLM:
    name = "cloud"

    def __init__(self, config: Config):
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "The cloud backend needs: pip install 'tone-architect[cloud]'"
            ) from exc

        self._anthropic = anthropic
        self._client = anthropic.Anthropic()
        self._config = config
        self._schema = structured_output_schema()

        if not (self._client.api_key or self._client.auth_token):
            raise RuntimeError(
                "No Anthropic credentials found. Export ANTHROPIC_API_KEY, or run "
                "`ant auth login`. Set TONE_BACKEND=local to use llama-server instead."
            )

    def complete(self, system: str, user: str) -> str:
        cfg = self._config
        kwargs: dict[str, Any] = {
            "model": cfg.cloud_model,
            "max_tokens": cfg.cloud_max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "thinking": {"type": "adaptive"},
            "output_config": {
                "effort": cfg.cloud_effort,
                "format": {"type": "json_schema", "schema": self._schema},
            },
        }

        try:
            message = self._client.messages.create(**kwargs)
        except self._anthropic.BadRequestError:
            kwargs.pop("output_config", None)
            kwargs["system"] = system + "\n\nReturn a single JSON object and nothing else."
            message = self._client.messages.create(**kwargs)

        return _first_text(message)

    def model_id(self) -> str:
        return self._config.cloud_model


def _first_text(message: Any) -> str:
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise RuntimeError(f"No text block in response (stop_reason={message.stop_reason!r})")


def json_only(text: str) -> str:
    """Strip a stray code fence, for the non-structured fallback path."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()
