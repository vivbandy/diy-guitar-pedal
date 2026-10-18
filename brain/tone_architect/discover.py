"""Discovery: find the gear a request needs on TONE3000 instead of only using your own library.

    request -> gear plan (LLM) -> one TONE3000 search per item -> candidates -> normal pipeline

The plan is a short shopping list ("Hiwatt DR103 head", "Big Muff", "Greenback 4x12 IR"). Each
item becomes one best-match search, so a request costs a handful of API calls — /tones/search is
heavily rate-limited. Discovered tones go through `tone_to_capture`, so `includes_cab` still comes
from TONE3000's `gear` field and the validator's cabinet rule still applies unchanged.

After a successful patch, only the captures the patch actually uses are added to your manifest
(and optionally downloaded), so the library grows with what you play.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .library import CaptureLibrary, ManifestLibrary
from .llm.base import LLMClient
from .models import Capture, CaptureManifest, Patch
from .retrieval.captures import score_captures
from .tone3000 import Tone3000Client, download, tone_to_capture

MAX_PLAN_ITEMS = 6
RESULTS_PER_ITEM = 3

ROLE_TO_GEARS = {
    "amp": "amp_amp-cab",
    "cab": "cab",
    "pedal": "pedal",
    "outboard": "outboard",
}

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "enum": sorted(ROLE_TO_GEARS)},
                    "query": {"type": "string"},
                },
                "required": ["role", "query"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

PLAN_SYSTEM = f"""You are a guitar gear expert. Given a tone request, list the captured gear
needed to recreate it, as search queries for TONE3000 (a library of NAM amp/pedal captures and
cabinet IRs).

Return JSON: {{"items": [{{"role": "amp|cab|pedal|outboard", "query": "..."}}]}}

- At most {MAX_PLAN_ITEMS} items. Only gear that is *captured*: amps, drive/fuzz/boost pedals,
  cabinets, outboard preamps. Delay, reverb, compression, EQ and modulation are built into the
  plugin — do not list them.
- Queries are short make/model names as people title captures: "Hiwatt DR103", "Big Muff",
  "Greenback 4x12", "Tube Screamer", "Fender Twin Reverb". No adjectives, no artist names.
- Always include exactly one amp. Include a cab item whenever the amp would be a head.
"""


@dataclass
class PlanItem:
    role: str
    query: str


def plan_gear(request: str, llm: LLMClient) -> list[PlanItem]:
    raw = llm.complete(PLAN_SYSTEM, f"TONE REQUEST:\n{request}", schema=PLAN_SCHEMA)
    try:
        items = json.loads(raw).get("items") or []
    except (ValueError, AttributeError):
        items = []

    plan: list[PlanItem] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        query = str(item.get("query", "")).strip()
        if role in ROLE_TO_GEARS and query and (role, query.lower()) not in seen:
            seen.add((role, query.lower()))
            plan.append(PlanItem(role, query))

    if not any(p.role == "amp" for p in plan):
        # A plan with no amp can't make a patch; fall back to searching the request itself.
        plan.insert(0, PlanItem("amp", request))
    # Ask for a cab even if the model forgot: an amp head with no IR available fails validation.
    if not any(p.role == "cab" for p in plan):
        plan.append(PlanItem("cab", "4x12"))
    return plan[:MAX_PLAN_ITEMS]


def discover_captures(
    plan: list[PlanItem], client: Tone3000Client, per_item: int = RESULTS_PER_ITEM
) -> list[Capture]:
    captures: dict[str, Capture] = {}
    for item in plan:
        for tone in client.search_top(item.query, gears=ROLE_TO_GEARS[item.role], limit=per_item):
            capture = tone_to_capture(tone)
            captures.setdefault(capture.id, capture)
    return list(captures.values())


class DiscoveryLibrary:
    """Your library plus this request's TONE3000 finds. Discovered captures are always offered to
    the model (they were searched for this request); your own library is ranked as usual."""

    def __init__(self, base: CaptureLibrary | None, discovered: list[Capture]):
        self.base = base
        self.discovered = discovered
        self._discovered_by_id = {c.id: c for c in discovered}

    def ids(self) -> set[str]:
        return set(self._discovered_by_id) | (self.base.ids() if self.base else set())

    def by_id(self, capture_id: str) -> Capture | None:
        found = self._discovered_by_id.get(capture_id)
        if found is None and self.base is not None:
            found = self.base.by_id(capture_id)
        return found

    def search(self, request: str, limit: int = 24) -> list[Capture]:
        own = self.base.search(request, limit=limit) if self.base else []
        merged = {c.id: c for c in [*self.discovered, *own]}
        return score_captures(list(merged.values()), request, limit=max(limit, len(merged)))


def used_capture_ids(patch: Patch) -> set[str]:
    return {
        node.params.capture_id
        for node in patch.chain
        if getattr(getattr(node, "params", None), "capture_id", None)
    }


def used_discoveries(patch: Patch, library: DiscoveryLibrary) -> list[Capture]:
    used = used_capture_ids(patch)
    base_ids = library.base.ids() if library.base else set()
    return [c for c in library.discovered if c.id in used and c.id not in base_ids]


def missing_tone3000_files(manifest_path: Path, only: set[str] | None = None) -> list[Capture]:
    """TONE3000 captures in the manifest whose model file isn't on disk yet."""
    library = ManifestLibrary.from_path(manifest_path)
    out = []
    for capture in library.all():
        if only is not None and capture.id not in only:
            continue
        path = library.resolve_file(capture.id)
        if _tone_id(capture) is not None and path is not None and not path.is_file():
            out.append(capture)
    return out


def save_to_manifest(captures: list[Capture], manifest_path: Path) -> CaptureManifest:
    if manifest_path.is_file():
        manifest = ManifestLibrary.from_path(manifest_path).manifest
    else:
        manifest = CaptureManifest(root="captures")
    by_id = {c.id: c for c in manifest.captures}
    by_id.update({c.id: c for c in captures})
    manifest = CaptureManifest(
        root=manifest.root, captures=sorted(by_id.values(), key=lambda c: c.id)
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json", exclude_none=True), indent=2) + "\n"
    )
    return manifest


def download_models(
    captures: list[Capture], client: Tone3000Client, manifest_path: Path
) -> list[str]:
    """Fetch the model file for each capture into the manifest's root. Returns failures."""
    library = ManifestLibrary.from_path(manifest_path)
    failures: list[str] = []
    for capture in captures:
        tone_id = _tone_id(capture)
        dest = library.resolve_file(capture.id)
        models = client.models(tone_id) if tone_id is not None else []
        if dest is None or not models or not models[0].get("model_url"):
            failures.append(capture.id)
            continue
        try:
            download(client, models[0]["model_url"], dest)
        except Exception:  # one failed download shouldn't lose the rest
            failures.append(capture.id)
    return failures


def _tone_id(capture: Capture) -> int | None:
    # tone_to_capture records "tone3000 id=<n>" first in notes.
    for part in (capture.notes or "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == "tone3000 id" and value.isdigit():
            return int(value)
    return None


def download_main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    from .tone3000_auth import AuthError, resolve_token

    parser = argparse.ArgumentParser(
        prog="tone3000-download",
        description="Download model files for TONE3000 captures in a manifest that aren't on "
        "disk yet (into the manifest's root folder).",
    )
    parser.add_argument("--manifest", "-m", default="captures.manifest.json")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest).expanduser()
    if not manifest_path.is_file():
        print(f"no manifest at {manifest_path}", file=sys.stderr)
        return 1
    missing = missing_tone3000_files(manifest_path)
    if not missing:
        print("nothing to download: every TONE3000 capture already has its file")
        return 0

    try:
        token, _ = resolve_token()
    except AuthError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    client = Tone3000Client(token)
    try:
        failed = download_models(missing, client, manifest_path)
    finally:
        client.close()

    library = ManifestLibrary.from_path(manifest_path)
    for capture in missing:
        if capture.id in failed:
            print(f"FAILED  {capture.name}", file=sys.stderr)
        else:
            print(f"OK      {capture.name}  ->  {library.resolve_file(capture.id)}")
    return 1 if failed else 0
