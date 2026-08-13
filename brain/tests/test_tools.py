from __future__ import annotations

import json

from tone_architect.config import DEFAULT_CLOUD_MODEL, Config
from tone_architect.models import CaptureCategory, Patch
from tone_architect.preset_writer import write_patch
from tone_architect.scaffold_manifest import scaffold
from tone_architect.tone3000 import tone_to_capture


def test_preset_write_is_atomic_and_leaves_no_temp_files(tmp_path, srv_patch):
    out = tmp_path / "patch.json"
    write_patch(Patch.model_validate(srv_patch), out)

    assert json.loads(out.read_text())["name"] == srv_patch["name"]
    assert [p.name for p in tmp_path.iterdir()] == ["patch.json"]


def test_preset_write_overwrites_cleanly(tmp_path, srv_patch, gilmour_patch):
    out = tmp_path / "patch.json"
    write_patch(Patch.model_validate(srv_patch), out)
    write_patch(Patch.model_validate(gilmour_patch), out)
    assert json.loads(out.read_text())["name"] == gilmour_patch["name"]


def test_scaffold_infers_categories(tmp_path):
    for name in (
        "marshall_plexi_head_crunch.nam",
        "fender_twin_fullrig_clean.nam",
        "greenback_412_cab.wav",
        "tubescreamer_od.nam",
    ):
        (tmp_path / name).write_bytes(b"")

    manifest = scaffold(tmp_path)
    by_id = {c.id: c for c in manifest.captures}

    assert by_id["marshall_plexi_head_crunch"].category is CaptureCategory.amp
    assert by_id["marshall_plexi_head_crunch"].includes_cab is False
    assert by_id["fender_twin_fullrig_clean"].includes_cab is True
    assert by_id["greenback_412_cab"].category is CaptureCategory.cab
    assert by_id["tubescreamer_od"].category is CaptureCategory.pedal


def test_tone3000_gear_populates_includes_cab():
    head = tone_to_capture({"id": 1, "title": "Plexi Head", "gear": "amp", "format": "nam"})
    rig = tone_to_capture({"id": 2, "title": "Twin Combo", "gear": "amp-cab", "format": "nam"})
    legacy = tone_to_capture({"id": 3, "title": "Old Rig", "gear": "full-rig", "format": "nam"})
    cab = tone_to_capture({"id": 4, "title": "V30 412", "gear": "cab", "format": "ir"})

    assert (head.category, head.includes_cab) == (CaptureCategory.amp, False)
    assert (rig.category, rig.includes_cab) == (CaptureCategory.amp, True)
    assert legacy.includes_cab is True
    assert cab.category is CaptureCategory.cab
    assert cab.format.value == "wav_ir"


def test_config_defaults_to_a_current_model(monkeypatch):
    monkeypatch.delenv("TONE_CLOUD_MODEL", raising=False)
    assert Config.load().cloud_model == DEFAULT_CLOUD_MODEL
    assert DEFAULT_CLOUD_MODEL.startswith("claude-")


def test_config_reads_the_environment(monkeypatch):
    monkeypatch.setenv("TONE_BACKEND", "local")
    monkeypatch.setenv("TONE_CLOUD_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("TONE_MAX_REPAIR_ATTEMPTS", "5")

    config = Config.load()
    assert config.backend == "local"
    assert config.cloud_model == "claude-sonnet-5"
    assert config.max_repair_attempts == 5


def test_config_never_carries_the_anthropic_key():
    """The SDK reads ANTHROPIC_API_KEY itself; Config must not copy it into a dataclass."""
    fields = set(Config.__dataclass_fields__)
    assert not any("anthropic" in f or f.endswith("api_key") for f in fields)
