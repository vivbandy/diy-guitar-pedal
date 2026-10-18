"""Populate the capture manifest from the TONE3000 API.

Why this exists: `includes_cab` is a correctness rule, and inferring it from a filename is a
guess. TONE3000 records it authoritatively as the tone's `gear` — `amp` is a head, `amp-cab` is a
full rig (the older `full-rig` value is a deprecated alias). Syncing from the API removes the
guess entirely.

Auth: `tone3000-login` signs you in (needed for --scope favorited/created, which are per-user).
TONE3000_TOKEN (the secret key) is the fallback and only works for --scope search. Never
hardcode either.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .models import Capture, CaptureCategory, CaptureFormat, CaptureGain, CaptureManifest
from .tone3000_auth import AuthError, resolve_token

API_BASE = os.getenv("TONE3000_API_BASE", "https://www.tone3000.com/api/v1")

GEAR_TO_CATEGORY: dict[str, CaptureCategory] = {
    "amp": CaptureCategory.amp,
    "amp-cab": CaptureCategory.amp,
    "full-rig": CaptureCategory.amp,
    "cab": CaptureCategory.cab,
    "pedal": CaptureCategory.pedal,
    "outboard": CaptureCategory.outboard,
    "space": CaptureCategory.outboard,
    "experimental": CaptureCategory.outboard,
}

FULL_RIG_GEARS = frozenset({"amp-cab", "full-rig"})

_GAIN_HINTS: list[tuple[CaptureGain, tuple[str, ...]]] = [
    (CaptureGain.fuzz, ("fuzz", "muff")),
    (CaptureGain.high_gain, ("high gain", "high-gain", "metal", "djent", "brutal")),
    (CaptureGain.mid_gain, ("lead", "overdrive", "drive", "rock")),
    (CaptureGain.crunch, ("crunch", "breakup", "edge of")),
    (CaptureGain.clean, ("clean", "sparkle", "chime")),
]


class Tone3000Client:
    def __init__(self, token: str, base: str = API_BASE):
        import httpx

        self._client = httpx.Client(
            base_url=base,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60.0,
        )

    def search(self, **params: Any) -> list[dict]:
        # /tones/search caps page_size at 25 and is heavily rate-limited.
        return self._paginate("/tones/search", params, page_size=25)

    def search_top(self, query: str, gears: str | None = None, limit: int = 10) -> list[dict]:
        """One page of best-match results — what discovery uses, to stay under the rate limit."""
        params = {"query": query, "gears": gears, "page": 1, "page_size": min(limit, 25)}
        response = self._client.get(
            "/tones/search", params={k: v for k, v in params.items() if v is not None}
        )
        response.raise_for_status()
        body = response.json()
        return list(body.get("data", body) if isinstance(body, dict) else body)[:limit]

    def favorited(self, **params: Any) -> list[dict]:
        return self._paginate("/tones/favorited", params)

    def created(self, **params: Any) -> list[dict]:
        return self._paginate("/tones/created", params)

    def models(self, tone_id: int, architecture: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"tone_id": tone_id}
        if architecture:
            params["architecture"] = architecture
        return self._paginate("/models", params)

    def _paginate(
        self, path: str, params: dict[str, Any], max_pages: int = 20, page_size: int = 50
    ) -> list[dict]:
        out: list[dict] = []
        page = 1
        while page <= max_pages:
            query = {k: v for k, v in params.items() if v is not None}
            query.update({"page": page, "page_size": page_size})
            response = self._client.get(path, params=query)
            response.raise_for_status()
            body = response.json()
            batch = body.get("data", body) if isinstance(body, dict) else body
            if not batch:
                break
            out.extend(batch)
            if len(batch) < page_size:
                break
            page += 1
        return out

    def close(self) -> None:
        self._client.close()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "capture"


def _gain_for(title: str, tags: list[str]) -> CaptureGain:
    haystack = " ".join([title, *tags]).lower()
    for gain, hints in _GAIN_HINTS:
        if any(h in haystack for h in hints):
            return gain
    return CaptureGain.n_a


def tone_to_capture(tone: dict, model: dict | None = None) -> Capture:
    gear = (tone.get("gear") or "").strip().lower()
    category = GEAR_TO_CATEGORY.get(gear, CaptureCategory.amp)
    fmt = CaptureFormat.wav_ir if (tone.get("format") or "nam") == "ir" else CaptureFormat.nam
    tags = [t["name"] for t in tone.get("tags") or [] if isinstance(t, dict) and t.get("name")]
    makes = [m["name"] for m in tone.get("makes") or [] if isinstance(m, dict) and m.get("name")]
    title = tone.get("title") or f"tone-{tone.get('id')}"

    suffix = "wav" if fmt is CaptureFormat.wav_ir else "nam"
    capture_id = slugify(f"t3k_{tone.get('id')}_{title}")[:64]

    return Capture(
        id=capture_id,
        name=title,
        file=f"{capture_id}.{suffix}",
        format=fmt,
        category=category,
        gain=_gain_for(title, tags) if category is not CaptureCategory.cab else CaptureGain.n_a,
        character=makes,
        tags=tags,
        source="tone3000",
        includes_cab=gear in FULL_RIG_GEARS,
        notes=_notes(tone, model),
    )


def _notes(tone: dict, model: dict | None) -> str | None:
    bits = [f"tone3000 id={tone.get('id')}", f"gear={tone.get('gear')}"]
    if tone.get("url"):
        bits.append(tone["url"])
    if model and model.get("model_url"):
        bits.append(f"model={model['id']}")
    return "; ".join(bits)


def build_manifest(
    client: Tone3000Client,
    query: str | None,
    gears: str | None,
    scope: str,
    architecture: str | None,
    download_dir: Path | None,
) -> CaptureManifest:
    fetch = {"search": client.search, "favorited": client.favorited, "created": client.created}[
        scope
    ]
    kwargs: dict[str, Any] = {"architecture": architecture}
    if scope == "search":
        kwargs.update({"query": query, "gears": gears})
    tones = fetch(**kwargs)

    captures: list[Capture] = []
    for tone in tones:
        model = None
        if download_dir is not None:
            models = client.models(tone["id"], architecture=architecture)
            model = models[0] if models else None
        capture = tone_to_capture(tone, model)
        if download_dir is not None and model and model.get("model_url"):
            download(client, model["model_url"], download_dir / capture.file)
        captures.append(capture)

    root = str(download_dir) if download_dir else "captures"
    return CaptureManifest(root=root, captures=captures)


def download(client: Tone3000Client, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    response = client._client.get(url, follow_redirects=True)
    response.raise_for_status()
    dest.write_bytes(response.content)


def merge(existing: CaptureManifest, incoming: CaptureManifest) -> CaptureManifest:
    """Incoming wins on id collision — the API is more authoritative than a hand-edited stub."""
    by_id = {c.id: c for c in existing.captures}
    by_id.update({c.id: c for c in incoming.captures})
    return CaptureManifest(
        root=existing.root or incoming.root,
        captures=sorted(by_id.values(), key=lambda c: c.id),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tone3000-sync",
        description="Build/merge a capture manifest from TONE3000 (sets includes_cab from `gear`).",
    )
    parser.add_argument("--query", "-q", help="text search (scope=search only)")
    parser.add_argument(
        "--gears",
        help="underscore-separated gear filter, e.g. amp_amp-cab_cab (search scope only)",
    )
    parser.add_argument("--scope", choices=("search", "favorited", "created"), default="favorited")
    parser.add_argument("--architecture", choices=("1", "2", "custom"), help="A1 / A2 / custom")
    parser.add_argument("--out", "-o", default="captures.manifest.json")
    parser.add_argument("--merge", action="store_true", help="merge into --out if it exists")
    parser.add_argument("--download", help="also download model files into this folder")
    args = parser.parse_args(argv)

    try:
        token, token_source = resolve_token()
    except AuthError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    client = Tone3000Client(token)
    try:
        manifest = build_manifest(
            client,
            args.query,
            args.gears,
            args.scope,
            args.architecture,
            Path(args.download).expanduser() if args.download else None,
        )
    finally:
        client.close()

    out = Path(args.out).expanduser()
    if args.merge and out.is_file():
        existing = CaptureManifest.model_validate(json.loads(out.read_text()))
        manifest = merge(existing, manifest)

    out.write_text(json.dumps(manifest.model_dump(mode="json", exclude_none=True), indent=2) + "\n")
    heads = sum(
        1 for c in manifest.captures if c.category is CaptureCategory.amp and not c.includes_cab
    )
    rigs = sum(1 for c in manifest.captures if c.category is CaptureCategory.amp and c.includes_cab)
    print(f"wrote {out}: {len(manifest.captures)} captures ({heads} amp heads, {rigs} full rigs)")
    if not manifest.captures and args.scope != "search" and token_source == "secret-key":
        print(
            f"hint: --scope {args.scope} is per-user and the secret key isn't a user; "
            "run tone3000-login first",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
