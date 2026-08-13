from __future__ import annotations

import copy

from conftest import amp_head_patch, full_rig_patch

from tone_architect.validate import validate_patch


def test_gilmour_example_is_valid(gilmour_patch, library):
    result = validate_patch(gilmour_patch, library)
    assert result.ok, result.error_text()
    assert result.warnings == []


def test_srv_example_is_valid(srv_patch, library):
    result = validate_patch(srv_patch, library)
    assert result.ok, result.error_text()
    assert result.warnings == []


def test_unknown_capture_id_is_rejected(gilmour_patch, library):
    patch = copy.deepcopy(gilmour_patch)
    patch["chain"][2]["params"]["capture_id"] = "not_a_real_amp"
    result = validate_patch(patch, library)
    assert not result.ok
    assert "does not exist in the library" in result.error_text()
    assert "hiwatt_dr103_clean" in result.error_text()


def test_out_of_range_param_is_rejected(gilmour_patch, library):
    patch = copy.deepcopy(gilmour_patch)
    patch["chain"][-1]["params"]["mix"] = 4.2
    result = validate_patch(patch, library)
    assert not result.ok
    assert "mix" in result.error_text()


def test_unknown_node_type_is_rejected(library):
    patch = {
        "schema_version": "1.0",
        "name": "bogus",
        "chain": [{"type": "teleporter", "params": {}}],
    }
    assert not validate_patch(patch, library).ok


def test_missing_tone_core_is_rejected(library):
    patch = {
        "schema_version": "1.0",
        "name": "effects only",
        "chain": [{"type": "delay", "params": {"time_ms": 400}}],
    }
    result = validate_patch(patch, library)
    assert not result.ok
    assert "no amp/cab core" in result.error_text()


def test_malformed_json_is_rejected(library):
    result = validate_patch('{"schema_version": "1.0", "name":', library)
    assert not result.ok
    assert "not valid JSON" in result.error_text()


def test_empty_chain_is_rejected(library):
    assert not validate_patch({"schema_version": "1.0", "name": "empty", "chain": []}, library).ok


# --- the four cabinet-pairing cases (Prime Directive 4) ---------------------


def test_amp_head_without_cab_is_an_error(library):
    result = validate_patch(amp_head_patch(cab=False), library)
    assert not result.ok
    assert "thin and harsh" in result.error_text()


def test_amp_head_with_cab_is_valid(library):
    result = validate_patch(amp_head_patch(cab=True), library)
    assert result.ok, result.error_text()
    assert result.warnings == []


def test_full_rig_without_cab_is_valid(library):
    result = validate_patch(full_rig_patch(cab=False), library)
    assert result.ok, result.error_text()
    assert result.warnings == []


def test_full_rig_with_cab_warns_but_passes(library):
    result = validate_patch(full_rig_patch(cab=True), library)
    assert result.ok, result.error_text()
    assert "double-cabs" in result.warning_text()


def test_disabled_cab_does_not_satisfy_an_amp_head(library):
    patch = amp_head_patch(cab=True)
    patch["chain"][1]["enabled"] = False
    assert not validate_patch(patch, library).ok


def test_disabled_amp_head_does_not_demand_a_cab(library):
    patch = amp_head_patch(cab=False)
    patch["chain"][0]["enabled"] = False
    result = validate_patch(patch, library)
    assert result.ok, result.error_text()


def test_cab_before_amp_still_counts(library):
    """The rule is about presence, not position — the plugin owns ordering."""
    patch = amp_head_patch(cab=True)
    patch["chain"].reverse()
    assert validate_patch(patch, library).ok


def test_pedal_capture_does_not_trigger_the_cab_rule(library):
    patch = {
        "schema_version": "1.0",
        "name": "pedal into full rig",
        "chain": [
            {"type": "nam_capture", "params": {"capture_id": "bigmuff_fuzz"}},
            {"type": "nam_capture", "params": {"capture_id": "fender_twin_fullrig_clean"}},
        ],
    }
    result = validate_patch(patch, library)
    assert result.ok, result.error_text()
    assert result.warnings == []
