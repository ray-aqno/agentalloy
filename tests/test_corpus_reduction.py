"""Tests for Phase 1 / Duplicate Consolidation — A1: Python Packaging.

Merges python/python-packaging-and-pyproject (deprecated) into
python/python-packaging-pyproject (keeper).  Verifies:

  - Deprecated skill has deprecated:true + superseded_by.
  - Keeper skill has absorbed all unique content from deprecated.
  - Fragment sequences remain contiguous after merge.
  - Both skills ingest cleanly (valid YAML, required fields).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PACKS_ROOT = Path(__file__).resolve().parent.parent / "src" / "agentalloy" / "_packs"


def _load_skill(skill_id: str, category: str = "python") -> dict:
    """Load a skill YAML from the packs directory."""
    path = _PACKS_ROOT / category / f"{skill_id}.yaml"
    assert path.exists(), f"Skill file not found: {path}"
    with open(path) as f:
        return yaml.safe_load(f)


def _fragment_sequences(skill: dict) -> list[int]:
    """Return the fragment sequence numbers in order."""
    frags = skill.get("fragments", [])
    return sorted([fr["sequence"] for fr in frags])


def _fragment_types(skill: dict) -> list[str]:
    """Return the fragment types in sequence order."""
    frags = skill.get("fragments", [])
    sorted_frags = sorted(frags, key=lambda f: f["sequence"])
    return [fr["fragment_type"] for fr in sorted_frags]


def _fragment_content_concat(skill: dict) -> str:
    """Concatenate all fragment content in sequence order."""
    frags = skill.get("fragments", [])
    sorted_frags = sorted(frags, key=lambda f: f["sequence"])
    return "\n\n".join(fr["content"].strip() for fr in sorted_frags)


def _raw_prose(skill: dict) -> str:
    """Return the raw_prose content."""
    return (skill.get("raw_prose") or "").strip()


# ---------------------------------------------------------------------------
# A7: FastAPI Background Tasks helpers
# ---------------------------------------------------------------------------

_A7_KEEPER_ID = "fastapi-async-and-background-tasks"
_A7_DEPRECATED_ID = "fastapi-background-tasks-deep"


def _load_a7_skill(skill_id: str) -> dict:
    """Load a FastAPI skill YAML from the packs directory."""
    path = _PACKS_ROOT / "fastapi" / f"{skill_id}.yaml"
    assert path.exists(), f"Skill file not found: {path}"
    with open(path) as f:
        return yaml.safe_load(f)


# These are the fragment contents unique to the deprecated A7 skill that
# must appear in the keeper's combined content after consolidation.
_A7_UNIQUE_DEPRECATED_SECTIONS = [
    # Multiple tasks example
    "bg.add_task(send_confirmation_email, saved)",
    # Async/sync distinction
    "Async tasks are awaited on the event loop",
    "Sync tasks run on the thread pool",
    # Dependency-injected background tasks
    "dependencies=[Depends(log_request)]",
    # Limits and when to outgrow
    "No durability",
    "No retry",
    "No isolation",
    "No scheduling",
    # When to use
    "send an email",
    # DB session pitfalls
    "request-scoped",
    "Pass IDs into background tasks, not ORM objects",
    # Common pitfalls
    "Returning task results to the client",
]


# ---------------------------------------------------------------------------
# A7: Deprecated flags
# ---------------------------------------------------------------------------


def test_a7_fastapi_background_tasks_deprecated_flags() -> None:
    """The deprecated skill must have deprecated:true and superseded_by set."""
    dep = _load_a7_skill(_A7_DEPRECATED_ID)

    # Must have deprecated flag
    assert dep.get("deprecated") is True, (
        f"{_A7_DEPRECATED_ID} must have deprecated: true"
    )

    # Must have superseded_by pointing to the keeper skill_id
    superseded = dep.get("superseded_by")
    assert superseded is not None, (
        f"{_A7_DEPRECATED_ID} must have superseded_by set"
    )
    assert superseded == _A7_KEEPER_ID, (
        f"superseded_by should point to '{_A7_KEEPER_ID}', "
        f"got '{superseded}'"
    )


# ---------------------------------------------------------------------------
# A7: Keeper has absorbed deprecated content
# ---------------------------------------------------------------------------


def test_a7_fastapi_background_tasks_keeper_has_absorbed_content() -> None:
    """Keeper must contain all unique content from the deprecated skill."""
    keeper = _load_a7_skill(_A7_KEEPER_ID)
    dep = _load_a7_skill(_A7_DEPRECATED_ID)

    # Combine raw_prose + all fragment content for the keeper
    keeper_text = _raw_prose(keeper) + "\n\n" + _fragment_content_concat(keeper)

    # Each unique deprecated section must appear somewhere in the keeper
    missing = []
    for section in _A7_UNIQUE_DEPRECATED_SECTIONS:
        if section not in keeper_text:
            missing.append(section)

    assert not missing, (
        f"Keeper is missing absorbed content from deprecated skill: {missing}"
    )


# ---------------------------------------------------------------------------
# A7: Fragment sequences are contiguous
# ---------------------------------------------------------------------------


def test_a7_fastapi_background_tasks_deprecated_sequences_contiguous() -> None:
    """Deprecated skill fragment sequences must be contiguous (no gaps)."""
    dep = _load_a7_skill(_A7_DEPRECATED_ID)
    seqs = _fragment_sequences(dep)
    expected = list(range(1, len(seqs) + 1))
    assert seqs == expected, (
        f"Deprecated skill fragment sequences are not contiguous: "
        f"got {seqs}, expected {expected}"
    )


def test_a7_fastapi_background_tasks_keeper_sequences_contiguous() -> None:
    """Keeper skill fragment sequences must be contiguous (no gaps)."""
    keeper = _load_a7_skill(_A7_KEEPER_ID)
    seqs = _fragment_sequences(keeper)
    expected = list(range(1, len(seqs) + 1))
    assert seqs == expected, (
        f"Keeper skill fragment sequences are not contiguous: "
        f"got {seqs}, expected {expected}"
    )


# ---------------------------------------------------------------------------
# A7: Both skills ingest cleanly
# ---------------------------------------------------------------------------


def test_a7_fastapi_background_tasks_deprecated_ingests_cleanly() -> None:
    """Deprecated skill must pass all ingest validation."""
    dep = _load_a7_skill(_A7_DEPRECATED_ID)
    errors = _validate_skill_ingest(dep, _A7_DEPRECATED_ID)
    assert not errors, f"Deprecated skill has ingest errors: {errors}"


def test_a7_fastapi_background_tasks_keeper_ingests_cleanly() -> None:
    """Keeper skill must pass all ingest validation."""
    keeper = _load_a7_skill(_A7_KEEPER_ID)
    errors = _validate_skill_ingest(keeper, _A7_KEEPER_ID)
    assert not errors, f"Keeper skill has ingest errors: {errors}"


# ---------------------------------------------------------------------------
# A7: Keeper still has its own unique content
# ---------------------------------------------------------------------------

_A7_KEEPER_UNIQUE_SECTIONS = [
    # Keeper-specific topics (with backticks as they appear in YAML)
    "`async def` vs `def` handlers",
    "blocking-the-loop trap",
    "`lifespan` is the modern startup/shutdown hook",
    "app.state",
    "Async DB sessions",
    "Concurrency model",
    "Async tests",
    "Anti-patterns",
]


def test_a7_fastapi_background_tasks_keeper_retains_unique_content() -> None:
    """Keeper must still contain its own unique content after merge."""
    keeper = _load_a7_skill(_A7_KEEPER_ID)
    keeper_text = _raw_prose(keeper) + "\n\n" + _fragment_content_concat(keeper)

    missing = []
    for section in _A7_KEEPER_UNIQUE_SECTIONS:
        if section not in keeper_text:
            missing.append(section)

    assert not missing, (
        f"Keeper lost its own unique content: {missing}"
    )


# ---------------------------------------------------------------------------
# A7: Deprecated skill retains its content (just marked deprecated)
# ---------------------------------------------------------------------------


def test_a7_fastapi_background_tasks_deprecated_retains_content() -> None:
    """Deprecated skill must retain all its original content."""
    dep = _load_a7_skill(_A7_DEPRECATED_ID)
    dep_text = _raw_prose(dep) + "\n\n" + _fragment_content_concat(dep)

    assert "bg.add_task(send_confirmation_email, saved)" in dep_text, (
        "Deprecated skill should retain multiple tasks content"
    )
    assert "No durability" in dep_text, (
        "Deprecated skill should retain limits content"
    )
    assert "Pass IDs into background tasks, not ORM objects" in dep_text, (
        "Deprecated skill should retain DB session pitfalls"
    )


# ---------------------------------------------------------------------------
# A1: Deprecated flags
# ---------------------------------------------------------------------------


def test_a1_python_packaging_deprecated_flags() -> None:
    """The deprecated skill must have deprecated:true and superseded_by set."""
    dep = _load_skill("python-packaging-and-pyproject")

    # Must have deprecated flag
    assert dep.get("deprecated") is True, (
        "python-packaging-and-pyproject must have deprecated: true"
    )

    # Must have superseded_by pointing to the keeper skill_id
    superseded = dep.get("superseded_by")
    assert superseded is not None, (
        "python-packaging-and-pyproject must have superseded_by set"
    )
    assert superseded == "python-packaging-pyproject", (
        f"superseded_by should point to 'python-packaging-pyproject', "
        f"got '{superseded}'"
    )


# ---------------------------------------------------------------------------
# A1: Keeper has absorbed deprecated content
# ---------------------------------------------------------------------------

# These are the fragment contents unique to the deprecated skill that
# must appear in the keeper's combined content after consolidation.
_UNIQUE_DEPRECATED_SECTIONS = [
    # Section: src layout
    "Use the src layout",
    # Section: editable install
    "Editable install for local development",
    # Section: dependencies and lockfiles
    "Dependencies and lockfiles",
    # Section: virtual environments
    "Virtual environments",
    # Section: versioning
    "Versioning",
    # Content: plugin ecosystem detail (extra prose in deprecated fragment 8)
    "importlib.metadata.entry_points",
]


def test_a1_python_packaging_keeper_has_absorbed_content() -> None:
    """Keeper must contain all unique content from the deprecated skill."""
    keeper = _load_skill("python-packaging-pyproject")
    dep = _load_skill("python-packaging-and-pyproject")

    # Combine raw_prose + all fragment content for the keeper
    keeper_text = _raw_prose(keeper) + "\n\n" + _fragment_content_concat(keeper)

    # Each unique deprecated section must appear somewhere in the keeper
    missing = []
    for section in _UNIQUE_DEPRECATED_SECTIONS:
        if section not in keeper_text:
            missing.append(section)

    assert not missing, (
        f"Keeper is missing absorbed content from deprecated skill: {missing}"
    )


# ---------------------------------------------------------------------------
# A1: Fragment sequences are contiguous
# ---------------------------------------------------------------------------


def test_a1_python_packaging_deprecated_sequences_contiguous() -> None:
    """Deprecated skill fragment sequences must be contiguous (no gaps)."""
    dep = _load_skill("python-packaging-and-pyproject")
    seqs = _fragment_sequences(dep)
    expected = list(range(1, len(seqs) + 1))
    assert seqs == expected, (
        f"Deprecated skill fragment sequences are not contiguous: "
        f"got {seqs}, expected {expected}"
    )


def test_a1_python_packaging_keeper_sequences_contiguous() -> None:
    """Keeper skill fragment sequences must be contiguous (no gaps)."""
    keeper = _load_skill("python-packaging-pyproject")
    seqs = _fragment_sequences(keeper)
    expected = list(range(1, len(seqs) + 1))
    assert seqs == expected, (
        f"Keeper skill fragment sequences are not contiguous: "
        f"got {seqs}, expected {expected}"
    )


# ---------------------------------------------------------------------------
# A1: Both skills ingest cleanly
# ---------------------------------------------------------------------------

_VALID_FRAGMENT_TYPES = {"execution", "rationale", "example", "guardrail", "verification", "setup"}
_REQUIRED_DOMAIN_FIELDS = {
    "skill_type", "skill_id", "canonical_name", "category",
    "skill_class", "domain_tags", "always_apply", "author",
    "change_summary", "raw_prose", "fragments",
}


def _validate_skill_ingest(skill: dict, skill_id: str) -> list[str]:
    """Return a list of validation errors (empty = clean)."""
    errors = []

    # Required fields
    for field in _REQUIRED_DOMAIN_FIELDS:
        if field not in skill:
            errors.append(f"Missing required field: {field}")

    # skill_type must be domain
    if skill.get("skill_type") != "domain":
        errors.append(f"skill_type must be 'domain', got '{skill.get('skill_type')}'")

    # skill_class must be domain
    if skill.get("skill_class") != "domain":
        errors.append(f"skill_class must be 'domain', got '{skill.get('skill_class')}'")

    # Must have at least one execution fragment
    frag_types = _fragment_types(skill)
    if "execution" not in frag_types:
        errors.append("Domain skill must have at least one execution fragment")

    # Fragment types must be valid
    for ft in frag_types:
        if ft not in _VALID_FRAGMENT_TYPES:
            errors.append(f"Invalid fragment_type: '{ft}'")

    # Sequences must be contiguous
    seqs = _fragment_sequences(skill)
    expected = list(range(1, len(seqs) + 1))
    if seqs != expected:
        errors.append(f"Fragment sequences not contiguous: {seqs}")

    return errors


def test_a1_python_packaging_deprecated_ingests_cleanly() -> None:
    """Deprecated skill must pass all ingest validation."""
    dep = _load_skill("python-packaging-and-pyproject")
    errors = _validate_skill_ingest(dep, "python-packaging-and-pyproject")
    assert not errors, f"Deprecated skill has ingest errors: {errors}"


def test_a1_python_packaging_keeper_ingests_cleanly() -> None:
    """Keeper skill must pass all ingest validation."""
    keeper = _load_skill("python-packaging-pyproject")
    errors = _validate_skill_ingest(keeper, "python-packaging-pyproject")
    assert not errors, f"Keeper skill has ingest errors: {errors}"


# ---------------------------------------------------------------------------
# A1: Keeper still has its own unique content
# ---------------------------------------------------------------------------

_KEEPER_UNIQUE_SECTIONS = [
    # [tool.*] Sections
    "[tool.*] Sections",
    # Dynamic Fields
    "Dynamic Fields",
    # PEP 735
    "PEP 735",
    # maturin
    "maturin",
    # flit-core
    "flit-core",
    # classifiers
    "classifiers",
    # keywords
    "keywords",
    # urls
    "urls",
    # PEP 639
    "PEP 639",
    # GUI scripts
    "gui-scripts",
]


def test_a1_python_packaging_keeper_retains_unique_content() -> None:
    """Keeper must still contain its own unique content after merge."""
    keeper = _load_skill("python-packaging-pyproject")
    keeper_text = _raw_prose(keeper) + "\n\n" + _fragment_content_concat(keeper)

    missing = []
    for section in _KEEPER_UNIQUE_SECTIONS:
        if section not in keeper_text:
            missing.append(section)

    assert not missing, (
        f"Keeper lost its own unique content: {missing}"
    )


# ---------------------------------------------------------------------------
# A1: Deprecated skill retains its content (just marked deprecated)
# ---------------------------------------------------------------------------


def test_a1_python_packaging_deprecated_retains_content() -> None:
    """Deprecated skill must retain all its original content."""
    dep = _load_skill("python-packaging-and-pyproject")
    dep_text = _raw_prose(dep) + "\n\n" + _fragment_content_concat(dep)

    # Must still have the src layout section
    assert "Use the src layout" in dep_text, (
        "Deprecated skill should retain src layout content"
    )

    # Must still have the versioning section
    assert "Versioning" in dep_text, (
        "Deprecated skill should retain versioning content"
    )

    # Must still have virtual environments
    assert "Virtual environments" in dep_text, (
        "Deprecated skill should retain virtual environments content"
    )


# ---------------------------------------------------------------------------
# A4: Fastify Error Handling — Deprecated flags
# ---------------------------------------------------------------------------


def test_a4_fastify_error_handling_deprecated_flags() -> None:
    """The deprecated skill must have deprecated:true and superseded_by set."""
    dep = _load_skill("fastify-error-handling", category="fastify")

    # Must have deprecated flag
    assert dep.get("deprecated") is True, (
        "fastify-error-handling must have deprecated: true"
    )

    # Must have superseded_by pointing to the keeper skill_id
    superseded = dep.get("superseded_by")
    assert superseded is not None, (
        "fastify-error-handling must have superseded_by set"
    )
    assert superseded == "fastify-error-handling-deep", (
        f"superseded_by should point to 'fastify-error-handling-deep', "
        f"got '{superseded}'"
    )


# ---------------------------------------------------------------------------
# A4: Fastify Error Handling — Keeper has absorbed deprecated content
# ---------------------------------------------------------------------------

# These are the fragment contents unique to the deprecated skill that
# must appear in the keeper's combined content after consolidation.
_A4_UNIQUE_DEPRECATED_SECTIONS = [
    # The error code list from the deprecated skill
    "FST_ERR_NOT_FOUND",
    "FST_ERR_OPTIONS_NOT_OBJ",
    "FST_ERR_CTP_INVALID_JSON_BODY",
    "FST_ERR_REP_ALREADY_SENT",
    "FST_ERR_SEND_INSIDE_ONERR",
    "FST_ERR_HANDLER_TIMEOUT",
    "FST_ERR_DUPLICATED_ROUTE",
    "FST_ERR_PLUGIN_VERSION_MISMATCH",
]


def test_a4_fastify_error_handling_keeper_has_absorbed_content() -> None:
    """Keeper must contain all unique content from the deprecated skill."""
    keeper = _load_skill("fastify-error-handling-deep", category="fastify")
    dep = _load_skill("fastify-error-handling", category="fastify")

    # Combine raw_prose + all fragment content for the keeper
    keeper_text = _raw_prose(keeper) + "\n\n" + _fragment_content_concat(keeper)

    # Each unique deprecated section must appear somewhere in the keeper
    missing = []
    for section in _A4_UNIQUE_DEPRECATED_SECTIONS:
        if section not in keeper_text:
            missing.append(section)

    assert not missing, (
        f"Keeper is missing absorbed content from deprecated skill: {missing}"
    )


# ---------------------------------------------------------------------------
# A4: Fragment sequences are contiguous
# ---------------------------------------------------------------------------


def test_a4_fastify_error_handling_deprecated_sequences_contiguous() -> None:
    """Deprecated skill fragment sequences must be contiguous (no gaps)."""
    dep = _load_skill("fastify-error-handling", category="fastify")
    seqs = _fragment_sequences(dep)
    expected = list(range(1, len(seqs) + 1))
    assert seqs == expected, (
        f"Deprecated skill fragment sequences are not contiguous: "
        f"got {seqs}, expected {expected}"
    )


def test_a4_fastify_error_handling_keeper_sequences_contiguous() -> None:
    """Keeper skill fragment sequences must be contiguous (no gaps)."""
    keeper = _load_skill("fastify-error-handling-deep", category="fastify")
    seqs = _fragment_sequences(keeper)
    expected = list(range(1, len(seqs) + 1))
    assert seqs == expected, (
        f"Keeper skill fragment sequences are not contiguous: "
        f"got {seqs}, expected {expected}"
    )


# ---------------------------------------------------------------------------
# A4: Both skills ingest cleanly
# ---------------------------------------------------------------------------


def test_a4_fastify_error_handling_deprecated_ingests_cleanly() -> None:
    """Deprecated skill must pass all ingest validation."""
    dep = _load_skill("fastify-error-handling", category="fastify")
    errors = _validate_skill_ingest(dep, "fastify-error-handling")
    assert not errors, f"Deprecated skill has ingest errors: {errors}"


def test_a4_fastify_error_handling_keeper_ingests_cleanly() -> None:
    """Keeper skill must pass all ingest validation."""
    keeper = _load_skill("fastify-error-handling-deep", category="fastify")
    errors = _validate_skill_ingest(keeper, "fastify-error-handling-deep")
    assert not errors, f"Keeper skill has ingest errors: {errors}"


# ---------------------------------------------------------------------------
# A4: Keeper still has its own unique content
# ---------------------------------------------------------------------------

_A4_KEEPER_UNIQUE_SECTIONS = [
    "setErrorHandler",
    "Validation Errors",
    "Error Codes vs Status",
    "404 and 405 Handlers",
    "onError Hook",
    "Encapsulation",
    "Error Logging Levels",
    "Async Errors",
    "Common Pitfalls",
    "Verification",
]


def test_a4_fastify_error_handling_keeper_retains_unique_content() -> None:
    """Keeper must still contain its own unique content after merge."""
    keeper = _load_skill("fastify-error-handling-deep", category="fastify")
    keeper_text = _raw_prose(keeper) + "\n\n" + _fragment_content_concat(keeper)

    missing = []
    for section in _A4_KEEPER_UNIQUE_SECTIONS:
        if section not in keeper_text:
            missing.append(section)

    assert not missing, (
        f"Keeper lost its own unique content: {missing}"
    )


# ---------------------------------------------------------------------------
# A4: Deprecated skill retains its content (just marked deprecated)
# ---------------------------------------------------------------------------


def test_a4_fastify_error_handling_deprecated_retains_content() -> None:
    """Deprecated skill must retain all its original content."""
    dep = _load_skill("fastify-error-handling", category="fastify")
    dep_text = _raw_prose(dep) + "\n\n" + _fragment_content_concat(dep)

    # Must still have the error code list
    assert "FST_ERR_NOT_FOUND" in dep_text, (
        "Deprecated skill should retain error code content"
    )

    # Must still have the overview
    assert "Fastify routes errors through a layered pipeline" in dep_text, (
        "Deprecated skill should retain overview content"
    )
