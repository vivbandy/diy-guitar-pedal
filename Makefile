PYTHON ?= python3.13
VENV   := .venv
BIN    := $(VENV)/bin
MANIFEST ?= examples/captures.manifest.example.json
OUT      ?= out/patch.json
CAPTURES ?= captures

.DEFAULT_GOAL := help

.PHONY: help venv install install-dev test lint fmt generate validate scaffold \
        db-sync t3k-sync plugin-test clean

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | expand -t24

venv: ## create the virtualenv (Python 3.11+)
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)

install: venv ## install the brain
	$(BIN)/pip install -e "brain[cloud]"

install-dev: venv ## install the brain with dev + all optional backends
	$(BIN)/pip install -e "brain[cloud,local,supabase,tone3000,dev]"

test: ## run the brain test suite
	cd brain && ../$(BIN)/python -m pytest -q

lint: ## ruff check + format check
	cd brain && ../$(BIN)/python -m ruff check . && ../$(BIN)/python -m ruff format --check .

fmt: ## ruff autoformat
	cd brain && ../$(BIN)/python -m ruff check --fix . && ../$(BIN)/python -m ruff format .

generate: ## REQUEST="..." generate a patch
	@test -n "$(REQUEST)" || { echo 'usage: make generate REQUEST="gilmour lead"'; exit 2; }
	$(BIN)/tone-architect "$(REQUEST)" --manifest $(MANIFEST) --out $(OUT)

validate: ## PATCH=... validate a patch against MANIFEST
	$(BIN)/tone-architect validate $(or $(PATCH),$(OUT)) --manifest $(MANIFEST) --strict

validate-examples: ## validate both shipped example patches
	$(BIN)/tone-architect validate examples/patch.example.gilmour.json -m $(MANIFEST) --strict
	$(BIN)/tone-architect validate examples/patch.example.srv.json -m $(MANIFEST) --strict

scaffold: ## CAPTURES=<dir> build a manifest stub from a captures folder
	$(BIN)/tone-scaffold-manifest $(CAPTURES) --out captures.manifest.json

db-sync: ## push manifest + recipes into Supabase (needs SUPABASE_URL / SUPABASE_KEY)
	$(BIN)/tone-sync --manifest $(MANIFEST) --recipes recipes/recipes.seed.jsonl

t3k-sync: ## build a manifest from TONE3000 (needs TONE3000_TOKEN)
	$(BIN)/tone3000-sync --scope favorited --out captures.manifest.json --merge

plugin-test: ## compile and run the plugin core tests (clang++, no cmake)
	./plugin/tests/run.sh

clean:
	rm -rf $(VENV) out plugin/tests/.build brain/.pytest_cache brain/.ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
