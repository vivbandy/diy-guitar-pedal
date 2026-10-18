from __future__ import annotations

import json

from conftest import FakeLLM

from tone_architect.config import Config
from tone_architect.discover import (
    DiscoveryLibrary,
    PlanItem,
    discover_captures,
    plan_gear,
    save_to_manifest,
    used_discoveries,
)
from tone_architect.library import ManifestLibrary
from tone_architect.pipeline import generate_patch

TONES = {
    ("Hiwatt DR103", "amp_amp-cab"): [
        {"id": 11, "title": "Hiwatt DR103 Head", "gear": "amp", "format": "nam"},
        {"id": 12, "title": "Hiwatt Custom 50 Combo", "gear": "amp-cab", "format": "nam"},
    ],
    ("Greenback 4x12", "cab"): [
        {"id": 21, "title": "Greenback 4x12", "gear": "cab", "format": "ir"},
    ],
    ("Big Muff", "pedal"): [
        {"id": 31, "title": "Big Muff Pi", "gear": "pedal", "format": "nam"},
    ],
}


class FakeClient:
    def __init__(self):
        self.searches: list[tuple[str, str | None, int]] = []

    def search_top(self, query, gears=None, limit=10):
        self.searches.append((query, gears, limit))
        return TONES.get((query, gears), [])[:limit]


def plan_json(*items: tuple[str, str]) -> str:
    return json.dumps({"items": [{"role": r, "query": q} for r, q in items]})


def test_plan_parses_items_and_dedupes():
    llm = FakeLLM(
        [
            plan_json(
                ("amp", "Hiwatt DR103"),
                ("pedal", "Big Muff"),
                ("amp", "hiwatt dr103"),
                ("cab", "Greenback 4x12"),
                ("reverb", "hall"),
            )
        ]
    )
    plan = plan_gear("gilmour lead", llm)
    assert [(p.role, p.query) for p in plan] == [
        ("amp", "Hiwatt DR103"),
        ("pedal", "Big Muff"),
        ("cab", "Greenback 4x12"),
    ]


def test_plan_always_has_an_amp_and_a_cab():
    plan = plan_gear("warm clean strat", FakeLLM(["not json"]))
    assert plan[0] == PlanItem("amp", "warm clean strat")
    assert any(p.role == "cab" for p in plan)


def test_one_search_per_item_with_gear_filter():
    client = FakeClient()
    plan = [PlanItem("amp", "Hiwatt DR103"), PlanItem("cab", "Greenback 4x12")]
    captures = discover_captures(plan, client)

    assert [s[:2] for s in client.searches] == [
        ("Hiwatt DR103", "amp_amp-cab"),
        ("Greenback 4x12", "cab"),
    ]
    by_name = {c.name: c for c in captures}
    assert by_name["Hiwatt DR103 Head"].includes_cab is False
    assert by_name["Hiwatt Custom 50 Combo"].includes_cab is True
    assert by_name["Greenback 4x12"].format.value == "wav_ir"


def _discovered_library(base=None) -> DiscoveryLibrary:
    plan = [
        PlanItem("amp", "Hiwatt DR103"),
        PlanItem("cab", "Greenback 4x12"),
        PlanItem("pedal", "Big Muff"),
    ]
    return DiscoveryLibrary(base, discover_captures(plan, FakeClient()))


def _patch(*nodes: dict) -> str:
    return json.dumps({"schema_version": "1.0", "name": "Discovered", "chain": list(nodes)})


HEAD = {"type": "nam_capture", "params": {"capture_id": "t3k_11_hiwatt_dr103_head"}}
CAB = {"type": "ir_cab", "params": {"capture_id": "t3k_21_greenback_4x12"}}


def test_cab_rule_still_applies_to_discovered_heads():
    library = _discovered_library()
    llm = FakeLLM([_patch(HEAD), _patch(HEAD, CAB)])

    result = generate_patch("gilmour lead", library, llm, config=Config())

    assert result.ok, result.errors
    assert result.attempts == 2  # the head without a cab was rejected first
    prompt = llm.calls[0][1]
    assert "t3k_11_hiwatt_dr103_head" in prompt and "t3k_21_greenback_4x12" in prompt


def test_only_used_captures_are_saved(tmp_path):
    library = _discovered_library()
    result = generate_patch("gilmour lead", library, FakeLLM([_patch(HEAD, CAB)]), config=Config())

    used = used_discoveries(result.patch, library)
    assert sorted(c.id for c in used) == ["t3k_11_hiwatt_dr103_head", "t3k_21_greenback_4x12"]

    path = tmp_path / "captures.manifest.json"
    save_to_manifest(used, path)
    saved = ManifestLibrary.from_path(path)
    assert saved.ids() == {"t3k_11_hiwatt_dr103_head", "t3k_21_greenback_4x12"}


def test_saving_merges_into_existing_manifest(tmp_path, manifest):
    path = tmp_path / "captures.manifest.json"
    path.write_text(json.dumps(manifest.model_dump(mode="json", exclude_none=True)))
    library = _discovered_library(base=ManifestLibrary.from_path(path))

    result = generate_patch("gilmour lead", library, FakeLLM([_patch(HEAD, CAB)]), config=Config())
    save_to_manifest(used_discoveries(result.patch, library), path)

    ids = ManifestLibrary.from_path(path).ids()
    assert manifest.ids() <= ids
    assert "t3k_11_hiwatt_dr103_head" in ids


def test_own_library_still_offered_alongside_discoveries(library):
    combined = _discovered_library(base=library)
    ids = {c.id for c in combined.search("gilmour comfortably numb lead")}
    assert "t3k_11_hiwatt_dr103_head" in ids
    assert "hiwatt_dr103_clean" in ids


def test_cli_discover_end_to_end(tmp_path, monkeypatch):
    from tone_architect import cli, tone3000

    llm = FakeLLM(
        [
            plan_json(("amp", "Hiwatt DR103"), ("cab", "Greenback 4x12")),
            _patch(HEAD, CAB),
        ]
    )
    monkeypatch.setattr("tone_architect.llm.factory.make_llm", lambda config: llm)
    monkeypatch.setattr(tone3000, "Tone3000Client", lambda token: _ClosableFakeClient())
    monkeypatch.setenv("TONE3000_TOKEN_FILE", str(tmp_path / "none.json"))
    monkeypatch.setenv("TONE3000_TOKEN", "t3k_cs_secret")
    monkeypatch.setenv("TONE_SOURCE", "file")

    manifest = tmp_path / "captures.manifest.json"
    out = tmp_path / "patch.json"
    code = cli.main(["gilmour lead", "--discover", "-m", str(manifest), "-o", str(out)])

    assert code == 0
    assert json.loads(out.read_text())["name"] == "Discovered"
    assert ManifestLibrary.from_path(manifest).ids() == {
        "t3k_11_hiwatt_dr103_head",
        "t3k_21_greenback_4x12",
    }


class _ClosableFakeClient(FakeClient):
    def close(self):
        pass
