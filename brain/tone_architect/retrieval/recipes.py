"""Keyword scoring over the recipe knowledge base.

`score_rows` works on plain dicts so the file source and the Supabase source share one ranking.
"""

from __future__ import annotations

from .captures import tokenize


def score_row(row: dict, request: str, tokens: set[str] | None = None) -> float:
    tokens = tokens if tokens is not None else tokenize(request)
    lowered = request.lower()
    score = 0.0

    for field in ("artist", "song"):
        value = (row.get(field) or "").strip()
        if value and value.lower() in lowered:
            score += 6.0
        elif value and tokens & tokenize(value):
            score += 2.5

    for tag in row.get("tags") or []:
        if tag.lower() in lowered:
            score += 2.0
        elif tokens & tokenize(tag):
            score += 1.0

    name = row.get("name") or ""
    score += 1.0 * len(tokens & tokenize(name))
    score += 0.5 * len(tokens & tokenize(row.get("description") or ""))
    return score


def score_rows(rows: list[dict], request: str, limit: int = 3) -> list[dict]:
    tokens = tokenize(request)
    scored = [(score_row(r, request, tokens), i, r) for i, r in enumerate(rows)]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [r for s, _, r in scored[:limit] if s > 0]


def format_recipes(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        who = " — ".join(x for x in (r.get("artist"), r.get("song")) if x)
        header = f"- {r.get('name', 'recipe')}" + (f" ({who})" if who else "")
        lines.append(header)
        if r.get("description"):
            lines.append(f"    {r['description']}")
        if r.get("chain_sketch"):
            lines.append("    chain: " + " -> ".join(r["chain_sketch"]))
    return "\n".join(lines)
