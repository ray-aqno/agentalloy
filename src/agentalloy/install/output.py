"""Human-readable output utilities for install subcommands.

Provides a ``--json`` flag, a central ``write_result`` dispatcher,
and render helpers so subcommands can emit clean terminal output by
default while still supporting machine-parsable JSON.

Exports
-------
add_json_flag, write_result, render_checklist, render_key_value,
render_action_result, render_table, render_model_recommendations,
print_rich, print_rich_stderr, should_output_json, should_output_human
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Optional rich import — graceful fallback
# ---------------------------------------------------------------------------
try:
    from rich.console import Console as _Console

    _rich_available = True
except ImportError:  # pragma: no cover
    _Console = None  # type: ignore[assignment,misc]
    _rich_available = False


def print_rich(text: str, *, stderr: bool = False) -> None:
    """Print *text* to stdout or stderr using rich if available, else plain."""
    _out = sys.stderr if stderr else sys.stdout
    if _rich_available and _Console is not None:
        console = _Console(
            file=_out, force_terminal=sys.stderr.isatty() if stderr else sys.stdout.isatty()
        )
        console.print(text)
    else:
        print(text, file=_out)


def print_rich_stderr(text: str) -> None:
    """Shortcut for ``print_rich(text, stderr=True)``."""
    print_rich(text, stderr=True)


# ---------------------------------------------------------------------------
# Flag helpers
# ---------------------------------------------------------------------------


def add_json_flag(p: argparse.ArgumentParser) -> None:
    """Add a ``--json`` flag to an argument parser.

    When set, ``write_result`` / ``should_output_json`` will emit JSON
    instead of human-readable output regardless of TTY status.
    """
    p.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        default=False,
        help="Emit machine-readable JSON instead of human-readable output.",
    )


def should_output_json(args: argparse.Namespace) -> bool:
    """Return True when JSON output is requested."""
    return bool(getattr(args, "json_output", False))


def should_output_human(args: argparse.Namespace) -> bool:
    """Return True when human-readable output is appropriate (not JSON, not quiet)."""
    return not should_output_json(args) and not getattr(args, "quiet", False)


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

RenderFn = Callable[[dict[str, Any]], str]


def write_result(
    result: dict[str, Any],
    args: argparse.Namespace,
    human_fn: RenderFn | None = None,
) -> None:
    """Emit *result* to stdout in the appropriate format.

    Logic:
    - ``--quiet`` → print nothing
    - ``--json``  → pretty-printed JSON
    - default     → human-readable via *human_fn* (falls back to JSON if None)

    This function does **not** handle file persistence or state recording —
    callers must do ``install_state.save_output_file()`` separately.
    """
    quiet = getattr(args, "quiet", False)
    if quiet:
        return

    if should_output_json(args):
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return

    # Human-readable output
    if human_fn is not None:
        sys.stdout.write(human_fn(result))
    else:
        # Fallback: render as JSON when no human renderer provided
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# Render helpers — plain text, optionally enriched with ANSI if rich present
# ---------------------------------------------------------------------------


def _green(text: str) -> str:
    """Wrap text in green ANSI if rich is available, else plain."""
    if _rich_available:
        return f"[green]{text}[/green]"
    return text


def _bold(text: str) -> str:
    if _rich_available:
        return f"[bold]{text}[/bold]"
    return text


def _dim(text: str) -> str:
    if _rich_available:
        return f"[dim]{text}[/dim]"
    return text


def _yellow(text: str) -> str:
    if _rich_available:
        return f"[yellow]{text}[/yellow]"
    return text


def _red(text: str) -> str:
    if _rich_available:
        return f"[red]{text}[/red]"
    return text


# ---------------------------------------------------------------------------
# Checklist renderer — list of (label, status) pairs
# ---------------------------------------------------------------------------


def render_checklist(
    items: list[tuple[str, str]],
    *,
    title: str | None = None,
) -> str:
    """Render a checklist of items with status indicators.

    Parameters
    ----------
    items:
        ``(label, status)`` tuples. Status values like ``"ok"``,
        ``"warn"``, ``"error"``, ``"skip"`` control the indicator.
    title:
        Optional heading line.
    """
    lines: list[str] = []
    if title:
        lines.append(_bold(title))
        lines.append("")

    for label, status in items:
        status_lower = status.lower()
        if status_lower == "ok":
            indicator = _green("✓")
        elif status_lower == "warn":
            indicator = _yellow("⚠")
        elif status_lower == "error":
            indicator = _red("✗")
        else:
            indicator = _dim("-")
        lines.append(f"  {indicator} {label}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Key-value renderer
# ---------------------------------------------------------------------------


def render_key_value(
    pairs: list[tuple[str, str]],
    *,
    title: str | None = None,
) -> str:
    """Render key-value pairs in a two-column layout.

    Parameters
    ----------
    pairs:
        ``(key, value)`` tuples.
    title:
        Optional heading line.
    """
    lines: list[str] = []
    if title:
        lines.append(_bold(title))
        lines.append("")

    for key, value in pairs:
        lines.append(f"  {_bold(key + ':')}  {value}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Action result renderer — action + key details
# ---------------------------------------------------------------------------


def render_action_result(result: dict[str, Any]) -> str:
    """Render a generic action result (action + details).

    Looks for common keys and renders them appropriately.
    """
    action = result.get("action", "unknown")
    lines: list[str] = []

    # Status indicator
    success_actions = {
        "verified_present",
        "seeded",
        "initialized_empty",
        "started",
        "enabled",
        "wired",
        "already_running",
    }
    if action in success_actions:
        lines.append(_green(f"  ✓ {action}"))
    elif action == "manual_required":
        lines.append(_yellow(f"  ⚠ {action}"))
    else:
        lines.append(f"  {action}")

    # Collect detail keys (skip schema_version, action itself)
    detail_keys: list[tuple[str, str]] = []
    skip = {"schema_version", "action", "error", "remediation", "warning", "hint"}
    for key, value in result.items():
        if key in skip or value is None:
            continue
        if isinstance(value, (list, dict)):
            continue
        detail_keys.append((key, str(value)))

    if detail_keys:
        lines.append(render_key_value(detail_keys).rstrip())

    # Warning
    if result.get("warning"):
        lines.append(_yellow(f"  WARNING: {result['warning']}"))

    # Error + remediation
    if result.get("error"):
        lines.append(_red(f"  ERROR: {result['error']}"))
    if result.get("remediation"):
        lines.append(_dim(f"  FIX:   {result['remediation']}"))

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Table renderer
# ---------------------------------------------------------------------------


def render_table(
    headers: list[str],
    rows: list[list[str]],
    *,
    title: str | None = None,
) -> str:
    """Render a simple text table.

    Parameters
    ----------
    headers:
        Column header labels.
    rows:
        List of row value lists.
    title:
        Optional heading line.
    """
    if not headers or not rows:
        text = ""
        if title:
            text = _bold(title) + "\n"
        return text + "\n"

    all_rows = [headers] + rows
    col_widths = [max(len(str(r[i])) for r in all_rows) for i in range(len(headers))]

    lines: list[str] = []
    if title:
        lines.append(_bold(title))
        lines.append("")

    def _row(values: list[str], *, bold: bool = False) -> str:
        cells = []
        for i, val in enumerate(values):
            w = col_widths[i]
            cell = str(val).ljust(w)
            if bold:
                cell = _bold(cell)
            cells.append(cell)
        return "    " + "  ".join(cells)

    lines.append(_row(headers, bold=True))
    lines.append("    " + "─" * (sum(col_widths) + 2 * (len(headers) - 1)))
    for row in rows:
        lines.append(_row([str(v) for v in row]))

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Model recommendations renderer
# ---------------------------------------------------------------------------


def render_model_recommendations(result: dict[str, Any]) -> str:
    """Render model recommendation results in a human-readable table format."""
    lines: list[str] = []
    lines.append(_bold("  Embedding Model Recommendations"))
    lines.append("")

    host = result.get("host_target", "")
    preset = result.get("preset", "")
    base_preset = result.get("base_preset", "")

    lines.append(f"  {_bold('Host target:')} {host}")
    lines.append(f"  {_bold('Preset:')}      {preset} (base: {base_preset})")
    lines.append("")

    options = result.get("options", [])
    if not options:
        lines.append("  No model options available.\n")
        return "\n".join(lines) + "\n"

    for i, opt in enumerate(options, 1):
        runner = opt.get("embed_runner", "?")
        model = opt.get("embed_model", "?")
        is_default = opt.get("default", False)
        hint = opt.get("embed_runner_install_hint", "")

        marker = _green(" ← default") if is_default else ""
        lines.append(f"  {i}. {_bold(runner)} — {model}{marker}")
        if hint:
            lines.append(f"     {_dim(hint)}")

    lines.append("")
    return "\n".join(lines) + "\n"
