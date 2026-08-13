"""The pydantic models and the canonical JSON Schema must not drift apart."""

from __future__ import annotations

import copy

import pytest
from conftest import amp_head_patch, full_rig_patch
from jsonschema import Draft202012Validator

from tone_architect.llm.cloud import structured_output_schema
from tone_architect.models import Patch
from tone_architect.schema_files import load_json_schema
from tone_architect.validate import json_schema_errors, validate_patch

PATCH_SCHEMA = "patch.schema.json"
MANIFEST_SCHEMA = "capture.manifest.schema.json"


@pytest.fixture(scope="module")
def patch_schema() -> dict:
    schema = load_json_schema(PATCH_SCHEMA)
    assert schema is not None, "schema/patch.schema.json must be reachable from the package"
    return schema


def test_canonical_schemas_are_themselves_valid(patch_schema):
    Draft202012Validator.check_schema(patch_schema)
    Draft202012Validator.check_schema(load_json_schema(MANIFEST_SCHEMA))


def test_node_types_match(patch_schema):
    schema_types = {
        d["properties"]["type"]["const"]
        for name, d in patch_schema["$defs"].items()
        if name != "node"
    }
    model_types = {
        arg.model_fields["type"].annotation.__args__[0]
        for arg in Patch.model_fields["chain"].annotation.__args__[0].__args__[0].__args__
    }
    assert model_types == schema_types


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(amp_head_patch(cab=True), id="amp-head+cab"),
        pytest.param(full_rig_patch(cab=False), id="full-rig"),
    ],
)
def test_models_and_json_schema_agree_on_valid_patches(payload, library):
    assert json_schema_errors(payload) == []
    assert validate_patch(payload, library).ok


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda p: p.update(schema_version="2.0"), id="wrong-version"),
        pytest.param(lambda p: p.update(chain=[]), id="empty-chain"),
        pytest.param(lambda p: p.update(unexpected="x"), id="extra-top-level-key"),
        pytest.param(
            lambda p: p["chain"][0]["params"].update(input_level_db=99), id="out-of-range"
        ),
        pytest.param(lambda p: p["chain"][0]["params"].update(nope=1), id="extra-param"),
    ],
)
def test_models_and_json_schema_agree_on_invalid_patches(mutate, library, gilmour_patch):
    payload = copy.deepcopy(gilmour_patch)
    mutate(payload)
    assert json_schema_errors(payload) != []
    assert not validate_patch(payload, library).ok


def test_examples_validate_against_the_canonical_schema(gilmour_patch, srv_patch):
    assert json_schema_errors(gilmour_patch) == []
    assert json_schema_errors(srv_patch) == []


def test_structured_output_schema_drops_unsupported_keywords():
    """The API strips numeric constraints — this asserts we don't send them and get a 400."""
    schema = structured_output_schema()
    banned = {"minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "oneOf"}
    found: list[str] = []

    def walk(node, path="$"):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in banned:
                    found.append(f"{path}.{key}")
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(schema)
    assert found == []


def test_structured_output_schema_still_pins_the_node_types():
    schema = structured_output_schema()
    consts = {
        d["properties"]["type"]["const"]
        for d in schema.get("$defs", {}).values()
        if "properties" in d and "const" in d["properties"].get("type", {})
    }
    assert {"nam_capture", "ir_cab", "drive", "eq", "delay", "reverb"} <= consts
