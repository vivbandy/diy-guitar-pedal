from __future__ import annotations

import json
from pathlib import Path

import pytest

from tone_architect.library import ManifestLibrary
from tone_architect.models import CaptureManifest

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "examples"


@pytest.fixture(scope="session")
def manifest() -> CaptureManifest:
    return CaptureManifest.model_validate(
        json.loads((EXAMPLES / "captures.manifest.example.json").read_text())
    )


@pytest.fixture(scope="session")
def library(manifest: CaptureManifest) -> ManifestLibrary:
    return ManifestLibrary(manifest, root=EXAMPLES)


@pytest.fixture(scope="session")
def gilmour_patch() -> dict:
    return json.loads((EXAMPLES / "patch.example.gilmour.json").read_text())


@pytest.fixture(scope="session")
def srv_patch() -> dict:
    return json.loads((EXAMPLES / "patch.example.srv.json").read_text())


def amp_head_patch(cab: bool) -> dict:
    """hiwatt_dr103_clean is an amp head (includes_cab=false)."""
    chain: list[dict] = [
        {"type": "nam_capture", "params": {"capture_id": "hiwatt_dr103_clean"}},
    ]
    if cab:
        chain.append({"type": "ir_cab", "params": {"capture_id": "greenback_412_cab"}})
    return {"schema_version": "1.0", "name": "amp head test", "chain": chain}


def full_rig_patch(cab: bool) -> dict:
    """fender_twin_fullrig_clean is a full rig (includes_cab=true)."""
    chain: list[dict] = [
        {"type": "nam_capture", "params": {"capture_id": "fender_twin_fullrig_clean"}},
    ]
    if cab:
        chain.append({"type": "ir_cab", "params": {"capture_id": "greenback_412_cab"}})
    return {"schema_version": "1.0", "name": "full rig test", "chain": chain}


class FakeLLM:
    """Returns each queued response in turn; records the prompts it was given."""

    name = "fake"

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, schema: dict | None = None) -> str:
        self.calls.append((system, user))
        return self.responses.pop(0) if self.responses else "{}"

    def model_id(self) -> str:
        return "fake-model"
