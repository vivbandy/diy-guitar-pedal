from __future__ import annotations

import json

from conftest import FakeLLM, amp_head_patch, full_rig_patch

from tone_architect.config import Config
from tone_architect.pipeline import generate_patch, run
from tone_architect.recipe_source import FileRecipeSource
from tone_architect.retrieval.captures import score_captures
from tone_architect.validate import validate_patch


def test_valid_first_try(library):
    llm = FakeLLM([json.dumps(full_rig_patch(cab=False))])
    result = generate_patch("warm clean strat", library, llm, config=Config())
    assert result.ok, result.errors
    assert result.attempts == 1


def test_repair_loop_recovers(library):
    bad = json.dumps(amp_head_patch(cab=False))
    good = json.dumps(amp_head_patch(cab=True))
    llm = FakeLLM([bad, good])

    result = generate_patch("gilmour lead", library, llm, config=Config())
    assert result.ok, result.errors
    assert result.attempts == 2

    repair_prompt = llm.calls[1][1]
    assert "VALIDATION ERRORS" in repair_prompt
    assert "thin and harsh" in repair_prompt


def test_repair_loop_is_bounded(library):
    bad = json.dumps(amp_head_patch(cab=False))
    llm = FakeLLM([bad] * 10)
    config = Config(max_repair_attempts=2)

    result = generate_patch("gilmour lead", library, llm, config=config)
    assert not result.ok
    assert result.attempts == 3
    assert len(llm.calls) == 3


def test_malformed_json_is_repaired(library):
    llm = FakeLLM(["not json at all", json.dumps(full_rig_patch(cab=False))])
    result = generate_patch("clean", library, llm, config=Config())
    assert result.ok
    assert "not valid JSON" in llm.calls[1][1]


def test_prompt_lists_only_real_captures(library):
    llm = FakeLLM([json.dumps(full_rig_patch(cab=False))])
    generate_patch("gilmour comfortably numb lead", library, llm, config=Config())

    user = llm.calls[0][1]
    assert "AVAILABLE CAPTURES:" in user
    assert "includes_cab=" in user
    assert "hiwatt_dr103_clean" in user
    assert "not_a_real_amp" not in user


def test_run_writes_and_stamps_the_patch(library, tmp_path):
    llm = FakeLLM([json.dumps(full_rig_patch(cab=False))])
    out = tmp_path / "nested" / "patch.json"

    result, path = run("srv warm clean", library, llm, out, config=Config())
    assert result.ok
    assert path == out

    written = json.loads(out.read_text())
    assert written["source_request"] == "srv warm clean"
    assert written["created_by"] == "fake-model"
    assert validate_patch(written, library).ok


def test_run_writes_nothing_on_failure(library, tmp_path):
    llm = FakeLLM([json.dumps(amp_head_patch(cab=False))] * 5)
    out = tmp_path / "patch.json"

    result, path = run("bad", library, llm, out, config=Config(max_repair_attempts=1))
    assert not result.ok
    assert path is None
    assert not out.exists()


def test_recipe_hints_reach_the_prompt(library):
    recipes = FileRecipeSource(
        [
            {
                "name": "Gilmour Comfortably Numb lead",
                "artist": "David Gilmour",
                "song": "Comfortably Numb",
                "tags": ["lead", "fuzz"],
                "description": "Big Muff into a clean British amp.",
                "chain_sketch": ["compressor", "fuzz", "clean amp", "delay 440ms"],
            }
        ]
    )
    llm = FakeLLM([json.dumps(full_rig_patch(cab=False))])
    generate_patch("David Gilmour Comfortably Numb lead", library, llm, Config(), recipes)

    user = llm.calls[0][1]
    assert "RECIPE HINTS:" in user
    assert "Big Muff" in user


def test_retrieval_always_offers_an_amp_and_a_cab(library):
    picked = score_captures(library.all(), "chiptune bleep bloop", limit=1)
    categories = {c.category.value for c in picked}
    assert "amp" in categories
    assert "cab" in categories
