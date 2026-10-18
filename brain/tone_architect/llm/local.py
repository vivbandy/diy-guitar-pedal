"""Local backend: llama.cpp's OpenAI-compatible server (`llama-server`).

Constrained decoding is the whole point of running locally — an unconstrained small model rarely
emits well-formed patch JSON. Current llama-server accepts a JSON Schema directly via
`response_format`, which is stricter and easier to keep in sync than the hand-written grammar, so
that is the default; `prompts/grammar/patch.gbnf` is used when TONE_LOCAL_GRAMMAR=1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import Config
from .cloud import structured_output_schema


def grammar_path() -> Path:
    return Path(__file__).resolve().parent.parent / "prompts" / "grammar" / "patch.gbnf"


class LocalLLM:
    name = "local"

    def __init__(self, config: Config, use_grammar: bool = False):
        import httpx

        self._httpx = httpx
        self._config = config
        self._use_grammar = use_grammar
        self._schema = structured_output_schema()

    def complete(self, system: str, user: str, schema: dict[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self._config.local_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 4096,
            "temperature": 0.2,
        }

        if self._use_grammar and schema is None:
            payload["grammar"] = grammar_path().read_text()
        else:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "patch" if schema is None else "output",
                    "schema": schema or self._schema,
                    "strict": True,
                },
            }

        url = self._config.local_url.rstrip("/") + "/chat/completions"
        response = self._httpx.post(url, json=payload, timeout=180.0)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def model_id(self) -> str:
        return f"local:{self._config.local_model}"
