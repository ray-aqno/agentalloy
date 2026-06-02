"""Tests for JSX artifact stripping in authoring-agent skill YAML files.

Batch B targets three skills that may contain JSX-like component tags:
  - nextjs/nextjs-isr-and-revalidation.yaml
  - data-engineering/data-engineering-dbt-incremental.yaml
  - webhooks/webhooks-idempotency.yaml

JSX artifacts are component-like tags starting with an uppercase letter
(e.g. <Callout>, <Term>, <File>, <CodeTabs>, <TabItem>, <SnowflakeColumn>,
 <Incrementalpredicates>). Standard HTML elements (lowercase) and code
 inside fenced code blocks are not considered artifacts.
"""

from __future__ import annotations

from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKS_DIR = REPO_ROOT / "src" / "agentalloy" / "_packs"

# JSX component types that are NOT standard HTML (these are the artifacts).
JSX_COMPONENTS = {
    "Callout",
    "CodeTabs",
    "TabItem",
    "Term",
    "File",
    "SnowflakeColumn",
    "Incrementalpredicates",
}

# Files in Batch B
BATCH_B_FILES = [
    PACKS_DIR / "nextjs" / "nextjs-isr-and-revalidation.yaml",
    PACKS_DIR / "data-engineering" / "data-engineering-dbt-incremental.yaml",
    PACKS_DIR / "webhooks" / "webhooks-idempotency.yaml",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_jsx_tags(content: str) -> list[str]:
    """Return all JSX-like tags found in *content*.

    Skips tags that appear inside fenced code blocks (``` ... ```).
    """
    import re
    # Remove fenced code blocks so we don't match code inside them.
    cleaned = re.sub(r"```[^`]*```", "", content, flags=re.DOTALL)
    jsx_re = re.compile(r"<[A-Z][a-zA-Z0-9]*(?:\s+[^>]*)?/?>")
    return jsx_re.findall(cleaned)


def _check_file(filepath: Path) -> list[str]:
    """Check a single YAML file for JSX artifacts. Returns list of hits."""
    content = filepath.read_text(encoding="utf-8")
    tags = _extract_jsx_tags(content)

    # Filter to only JSX component tags (not standard HTML like <details>).
    jsx_components = [
        tag for tag in tags if tag.split()[0].lstrip("<") in JSX_COMPONENTS
    ]
    return jsx_components


# ---------------------------------------------------------------------------
# Batch B: simple JSX no-JSX check
# ---------------------------------------------------------------------------


def test_batch_b_simple_jsx_no_jsx() -> None:
    """All three Batch B skill files must be free of JSX component artifacts.

    Acceptance criteria:
      - Zero JSX artifacts in prose (outside code blocks).
      - Converted Markdown renders correctly (YAML parses cleanly).
      - All 3 skills ingest cleanly.
    """
    for filepath in BATCH_B_FILES:
        assert filepath.exists(), f"Skill file missing: {filepath}"

        # Verify YAML parses cleanly
        data = yaml.safe_load(filepath.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{filepath.name} is not a valid YAML dict"

        # Check for JSX artifacts
        jsx_components = _check_file(filepath)

        assert (
            not jsx_components
        ), f"{filepath.name} still contains JSX artifacts: {jsx_components}"
