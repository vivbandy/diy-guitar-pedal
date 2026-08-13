"""parse -> retrieve -> generate -> validate(+repair) -> write preset.

Runs entirely off the audio thread; its only output is a validated patch.json that the plugin
picks up later.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .library import CaptureLibrary
from .llm.base import LLMClient
from .models import Patch
from .preset_writer import write_patch
from .recipe_source import NullRecipeSource, RecipeSource
from .retrieval.captures import format_candidates
from .retrieval.recipes import format_recipes
from .validate import ValidationResult, validate_patch

_PROMPT = Path(__file__).resolve().parent / "prompts" / "system_parse.md"


def system_prompt() -> str:
    return _PROMPT.read_text()


@dataclass
class GenerationResult:
    ok: bool
    patch: Patch | None
    attempts: int
    errors: list[str]
    warnings: list[str]
    raw: str


def _build_user_message(
    request: str,
    library: CaptureLibrary,
    recipes: RecipeSource,
    config: Config,
) -> str:
    candidates = library.search(request, limit=config.max_candidates)
    hints = recipes.lookup(request, limit=config.max_recipes)

    parts = [f"TONE REQUEST:\n{request}", "", "AVAILABLE CAPTURES:", format_candidates(candidates)]
    if hints:
        parts += ["", "RECIPE HINTS:", format_recipes(hints)]
    parts += ["", "Return the patch JSON now."]
    return "\n".join(parts)


def generate_patch(
    request: str,
    library: CaptureLibrary,
    llm: LLMClient,
    config: Config | None = None,
    recipes: RecipeSource | None = None,
) -> GenerationResult:
    config = config or Config.load()
    recipes = recipes or NullRecipeSource()

    system = system_prompt()
    user = _build_user_message(request, library, recipes, config)

    raw = ""
    result = ValidationResult(ok=False, errors=["no attempt made"])

    for attempt in range(config.max_repair_attempts + 1):
        raw = llm.complete(system, user)
        result = validate_patch(raw, library)
        if result.ok:
            return GenerationResult(
                ok=True,
                patch=result.patch,
                attempts=attempt + 1,
                errors=[],
                warnings=result.warnings,
                raw=raw,
            )
        user = _repair_message(user, raw, result)

    return GenerationResult(
        ok=False,
        patch=result.patch,
        attempts=config.max_repair_attempts + 1,
        errors=result.errors,
        warnings=result.warnings,
        raw=raw,
    )


def _repair_message(previous_user: str, raw: str, result: ValidationResult) -> str:
    return (
        f"{previous_user}\n\n"
        "Your previous answer was rejected by the validator.\n\n"
        f"PREVIOUS OUTPUT:\n{raw}\n\n"
        f"VALIDATION ERRORS:\n{result.error_text()}\n\n"
        "Fix every error and return the corrected patch JSON only."
    )


def run(
    request: str,
    library: CaptureLibrary,
    llm: LLMClient,
    out_path: str | Path,
    config: Config | None = None,
    recipes: RecipeSource | None = None,
) -> tuple[GenerationResult, Path | None]:
    result = generate_patch(request, library, llm, config=config, recipes=recipes)
    if not result.ok or result.patch is None:
        return result, None

    if not result.patch.source_request:
        result.patch.source_request = request
    if not result.patch.created_by:
        result.patch.created_by = getattr(llm, "model_id", lambda: llm.name)()

    return result, write_patch(result.patch, out_path)
