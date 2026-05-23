#!/usr/bin/env python3
"""Bulk rename script: agentalloy -> agentalloy.

Case-preserving replacement:
  - AGENTALLOY -> AGENTALLOY  (env vars)
  - Skillsmit -> AgentAlloy   (user-facing prose)
  - agentalloy -> agentalloy  (code, paths, filenames)
  - Mixed case handled proportionally

Usage:
  python scripts/rebrand_rename.py --dry-run   # show diff, no writes
  python scripts/rebrand_rename.py              # apply changes
"""

import argparse
import difflib
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {'.git', '.venv', '__pycache__', '.hermes', '.mypy_cache', '.ruff_cache', '.pytest_cache', '.pytype'}
EXCLUDE_FILES = {'uv.lock', '.cgr-hash-cache.json', '.cgr-stat-cache.json'}

# Regex: match "agentalloy" case-insensitively
PATTERN = re.compile(r'agentalloy', re.IGNORECASE)


def case_preserve_replacement(match: re.Match) -> str:
    """Replace 'agentalloy' with 'agentalloy', preserving the case pattern."""
    original = match.group(0)

    # Full uppercase -> full uppercase
    if original.isupper():
        return 'AGENTALLOY'
    # Full lowercase -> full lowercase
    if original.islower():
        return 'agentalloy'
    # Title case (first char upper, rest lower) -> title case
    if original[0].isupper() and original[1:].islower():
        return 'AgentAlloy'
    # Mixed case: apply proportionally
    result = []
    target = 'agentalloy'
    for i, (orig_char, target_char) in enumerate(zip(original, target)):
        if orig_char.isupper():
            result.append(target_char.upper())
        else:
            result.append(target_char.lower())
    return ''.join(result)


def should_skip(path: Path) -> bool:
    """Check if a file should be skipped."""
    parts = path.parts
    # Skip excluded directories
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
    # Skip excluded files
    if path.name in EXCLUDE_FILES:
        return True
    return False


def collect_files() -> list[Path]:
    """Walk repo and collect all non-binary text files."""
    files = []
    for root, dirs, filenames in os.walk(REPO_ROOT):
        # Prune excluded dirs in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in sorted(filenames):
            fpath = Path(root) / fname
            if should_skip(fpath):
                continue
            # Skip binary files
            if fpath.suffix in {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.pdf', '.whl', '.tar', '.gz'}:
                continue
            try:
                content = fpath.read_text(encoding='utf-8')
            except (UnicodeDecodeError, PermissionError):
                continue
            files.append((fpath, content))
    return files


def apply_replacements(content: str) -> str:
    """Apply case-preserving replacement."""
    return PATTERN.sub(case_preserve_replacement, content)


def main():
    parser = argparse.ArgumentParser(description='Rename agentalloy to agentalloy')
    parser.add_argument('--dry-run', action='store_true', help='Show diff without writing')
    args = parser.parse_args()

    files = collect_files()
    changes = []

    for fpath, content in files:
        new_content = apply_replacements(content)
        if new_content != content:
            rel = fpath.relative_to(REPO_ROOT)
            changes.append((rel, content, new_content))

    if not changes:
        print("No changes found.")
        return

    print(f"Found {len(changes)} files to change\n")

    for rel, old, new in changes:
        if args.dry_run:
            # Show diff
            diff = difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=str(rel),
                tofile=str(rel),
                lineterm='',
            )
            print(''.join(diff))
        else:
            (REPO_ROOT / rel).write_text(new, encoding='utf-8')
            print(f"  {rel}")

    if args.dry_run:
        print(f"\nDry run complete. {len(changes)} files would change. Rerun without --dry-run to apply.")
    else:
        print(f"\nApplied changes to {len(changes)} files.")


if __name__ == '__main__':
    main()
