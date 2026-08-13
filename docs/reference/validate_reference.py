"""Patch validation: structural (pydantic/JSON-schema) + semantic (capture existence + cab pairing).

The pipeline never trusts raw model output. It runs `validate_patch` and, on failure, feeds the
human-readable error back to the model for a bounded repair loop.

The cab-pairing check is what prevents the classic "thin and harsh" mistake: an amp-HEAD capture
(no built-in cabinet) MUST be followed by a cab IR. Full-rig captures must NOT be (double-cab).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from .models import CaptureManifest, Patch

if TYPE_CHECKING:
    from .library import CaptureLibrary


@dataclass
class ValidationResult:
    ok: bool
    patch: Patch | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error_text(self) -> str:
        return "\n".join(f"- {e}" for e in self.errors)

    def warning_text(self) -> str:
        return "\n".join(f"- {w}" for w in self.warnings)


def validate_patch(
    raw: dict | str, manifest: "CaptureManifest | CaptureLibrary"
) -> ValidationResult:
    """Validate raw model output into a Patch.

    Gates:
      1. Structural — matches the Patch model (types, ranges, required fields)?
      2. Existence  — every referenced capture_id exists in the user's library?
      3. Tone core  — at least one amp/cab node present?
      4. Cab pairing — amp heads have a cab IR; full rigs don't double-cab.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            return ValidationResult(ok=False, errors=[f"Output is not valid JSON: {exc}"])

    # Gate 1: structure
    try:
        patch = Patch.model_validate(raw)
    except ValidationError as exc:
        return ValidationResult(ok=False, errors=[_fmt(e) for e in exc.errors()])

    # Gate 2: capture references must exist
    known = manifest.ids()
    missing = [cid for cid in patch.capture_ids() if cid not in known]
    if missing:
        avail = ", ".join(sorted(known)) or "(none)"
        return ValidationResult(
            ok=False,
            patch=patch,
            errors=[
                f"capture_id '{cid}' does not exist in the library. Choose only from: {avail}"
                for cid in missing
            ],
        )

    # Gate 3: tone core
    if not any(n.type in ("nam_capture", "ir_cab") for n in patch.chain):
        return ValidationResult(
            ok=False,
            patch=patch,
            errors=["Patch has no nam_capture or ir_cab node — there is no amp/cab core."],
        )

    # Gate 4: cab pairing
    errors, warnings = _cab_pairing(patch, manifest)
    if errors:
        return ValidationResult(ok=False, patch=patch, errors=errors, warnings=warnings)

    return ValidationResult(ok=True, patch=patch, warnings=warnings)


def _cab_pairing(patch: Patch, manifest) -> tuple[list[str], list[str]]:
    """Enforce the amp-head/full-rig cabinet rule.

    - amp HEAD (includes_cab=False) present and NO ir_cab in the chain -> error (thin tone).
    - full RIG (includes_cab=True) present together with an ir_cab     -> warning (double cab).
    """
    errors: list[str] = []
    warnings: list[str] = []

    has_ir_cab = any(n.type == "ir_cab" and n.enabled for n in patch.chain)
    has_amp_head = False
    has_full_rig = False

    for node in patch.chain:
        if node.type == "nam_capture" and node.enabled:
            cap = manifest.by_id(node.params.capture_id)
            if cap is None or cap.category.value != "amp":
                continue
            if cap.includes_cab:
                has_full_rig = True
            else:
                has_amp_head = True

    if has_amp_head and not has_ir_cab:
        errors.append(
            "This patch uses an amp-HEAD capture (no built-in speaker cab) but includes no "
            "ir_cab node. Add a cab IR (a 'cab' capture) right after the amp, or the tone will "
            "sound thin and harsh. Pick a cab from the available captures."
        )
    if has_full_rig and has_ir_cab:
        warnings.append(
            "This patch pairs a FULL-RIG capture (amp + cab already included) with a separate "
            "cab IR. That double-cabs the signal and usually sounds over-filtered — drop the "
            "ir_cab, or switch the amp to an amp-head capture."
        )
    return errors, warnings


def _fmt(err: dict) -> str:
    loc = ".".join(str(p) for p in err.get("loc", ()))
    return f"{loc}: {err.get('msg', 'invalid')}"


def load_manifest(path: str | Path) -> CaptureManifest:
    data = json.loads(Path(path).read_text())
    return CaptureManifest.model_validate(data)
