# `skillsmith setup` Wizard UX Overhaul — Implementation Spec

## Summary

This PR overhauls the interactive UX of the `skillsmith setup` wizard implemented
in `src/skillsmith/install/subcommands/simple_setup.py`. It fixes a cluster of
correctness bugs (stale `argparse` choices, missing input normalization, a bogus
sentinel for "runner unset", and a hardware label rendered with `.title()`),
reorders the question flow so hardware detection happens immediately before the
hardware prompt, deduplicates the post-prompt summary table, removes an
implementation-detail field (`Preset:`) from the user-visible review, and
replaces the four most ambiguous free-text prompts (runner, service mode,
hardware target, harness) with numbered menus. It also tightens wording on the
port and service-mode descriptions and standardizes the `[default]` marker
across all prompts.

All changes are confined to `src/skillsmith/install/subcommands/simple_setup.py`.
No subcommand internals are modified except for the `add_parser` argparse
choices on the `setup` subparser itself.

Out of scope: pack selection UX, any subcommand internals beyond
`add_parser` fixes inside `simple_setup.py`.

## Relationship to the build-sequence specs

This spec **must land before** `docs/build-sequence/01-foundation.md`
Step 1.5 (profile-aware setup + refuse-if-existing). Phase 1 layers
profile-detection, datastore-per-profile routing, and a `--force` flag
on top of the cleaned-up wizard. Its acceptance criteria and line
references assume this UX overhaul is already in.

If Phase 1 lands first, this spec's line numbers (422–433, 461–470,
477–504, 507–533, 541–551, etc.) go stale and the diff becomes
significantly harder to review.

After this lands, the new numbered-menu helpers (`_prompt_numbered`,
`_prompt_runner`, etc.) become the natural extension point for any
profile-selection menu Phase 1 needs.

---

## 1. Bugs

### B1 — `add_parser` `--runner` choices are stale (and audit `--harness` / `--hardware`)

**Description.** The CLI uses `argparse` `choices=` to validate `--runner`.
`lm-studio` was added to the wizard's runner logic but the argparse list was
never updated, so `skillsmith setup --runner lm-studio` is rejected by argparse
before the wizard ever runs. We also need to audit `--harness` and `--hardware`
for the same staleness. `--hardware` currently lists the correct four values.
`--harness` currently has no `choices=` (free-form string passed through to
`wire_harness`), which is intentional because the valid list lives in
`wire_harness.VALID_HARNESSES`; do **not** add a `choices=` list to
`--harness` — leave validation to the wizard body (which now does it against
`VALID_HARNESSES`). Only `--runner` needs the fix.

**File / location.** `src/skillsmith/install/subcommands/simple_setup.py`,
inside `add_parser`, around lines 721–726.

**Before:**

```python
p.add_argument(
    "--runner",
    choices=["ollama", "llama-server"],
    default=None,
    help="Embedding runner (default: ollama).",
)
```

**After:**

```python
p.add_argument(
    "--runner",
    choices=["ollama", "lm-studio", "llama-server"],
    default=None,
    help="Embedding runner (default: ollama).",
)
```

No change to `--harness` or `--hardware` in `add_parser`.

---

### B2 — `cfg.runner` is not normalized

**Description.** `cfg.harness` and `cfg.hardware_target` are normalized with
`.strip().lower()` after user input but `cfg.runner` is not. A user who types
` Ollama ` at the runner prompt will fail validation and exit. Apply the same
normalization.

**File / location.** `src/skillsmith/install/subcommands/simple_setup.py`,
runner block around lines 422–433. (Note: after N1 below, the runner block is
replaced by a numbered-menu helper that yields a canonical value directly, so
normalization there becomes a one-liner safety net rather than a behavioral
fix. Apply normalization regardless to defend against the `--runner` path,
where the value comes straight from argparse.)

**Before:**

```python
# 1. Runner
if cfg.runner == "ollama" and not cfg.non_interactive:
    cfg.runner = _prompt_context(
        "  Embedding runner",
        "  How to run the embedding model for skills retrieval:\n"
        "    ollama       - Ollama (recommended for most users)\n"
        "    llama-server - llama.cpp server (for GGUF models)",
        default="ollama",
    )
if cfg.runner not in ("ollama", "llama-server"):
    _print(f"  [red]Invalid runner: {cfg.runner}. Choose ollama or llama-server.[/red]")
    return 1
_print(f"  Runner: {cfg.runner}")
```

**After (combined with B3 and N1; see those sections for the final form):**

```python
# 1. Runner
if cfg.runner is None and not cfg.non_interactive:
    cfg.runner = _prompt_runner()
elif cfg.runner is None:
    cfg.runner = "ollama"
cfg.runner = cfg.runner.strip().lower()
if cfg.runner not in ("ollama", "lm-studio", "llama-server"):
    _print(
        f"  [red]Invalid runner: {cfg.runner}. "
        "Choose ollama, lm-studio, or llama-server.[/red]"
    )
    return 1
_print(f"  Runner: {cfg.runner}")
```

---

### B3 — `if cfg.runner == "ollama"` used as an "unset" sentinel

**Description.** Line 422 reads `if cfg.runner == "ollama" and not cfg.non_interactive:`
to decide whether to prompt the user for the runner. This conflates "user did
not provide `--runner`" with "user explicitly passed `--runner ollama`": the
latter still triggers the prompt. The correct sentinel is `None`. This requires
three coordinated changes:

1. `SetupConfig.runner` dataclass default → `None` (typed `str | None`).
2. `_run_from_args` must pass `args.runner` through **without** coalescing to
   `"ollama"`, so the wizard can tell "not set" from "set to ollama".
3. The wizard branch becomes `if cfg.runner is None and not cfg.non_interactive`,
   with a non-interactive fallback to `"ollama"`.

There is also a downstream consequence in `_run_from_args` lines 776–777 which
resolves the default model from `cfg.runner`. With `cfg.runner` possibly `None`,
defer the model default until after the runner is finalized inside `run_setup`.

**Files / locations.**

- `SetupConfig` dataclass, around lines 58–75.
- `_run_from_args`, around lines 763–778.
- Runner block in `run_setup`, around lines 422–433.
- Model block in `run_setup`, around lines 436–444 (already uses
  `_MODEL_DEFAULTS.get(cfg.runner, ...)` and will need `cfg.runner` to be
  finalized first — it already is in the existing ordering, but verify after
  edits).

**Before — `SetupConfig.runner`:**

```python
@dataclass
class SetupConfig:
    """User-facing configuration gathered during the interactive wizard."""

    runner: str = "ollama"
    model: str = "qwen3-embedding:0.6b"
```

**After:**

```python
@dataclass
class SetupConfig:
    """User-facing configuration gathered during the interactive wizard."""

    runner: str | None = None
    model: str = "qwen3-embedding:0.6b"
```

**Before — `_run_from_args`:**

```python
def _run_from_args(args: argparse.Namespace) -> int:
    """Bridge from argparse.Namespace to SetupConfig -> run_setup()."""
    cfg = SetupConfig(
        runner=args.runner or "ollama",
        model=args.model or "",
        port=args.port or 47950,
        mode=args.mode or "persistent",
        packs=args.packs or "",
        harness=args.harness or "manual",
        hardware_target=getattr(args, "hardware", None) or "",
        non_interactive=args.non_interactive,
    )
    # Override model default based on runner if not explicitly set
    if cfg.model == "":
        cfg.model = _MODEL_DEFAULTS.get(cfg.runner, "qwen3-embedding:0.6b")
    return run_setup(cfg)
```

**After:**

```python
def _run_from_args(args: argparse.Namespace) -> int:
    """Bridge from argparse.Namespace to SetupConfig -> run_setup()."""
    cfg = SetupConfig(
        runner=args.runner,  # may be None; resolved inside run_setup
        model=args.model or "",
        port=args.port or 47950,
        mode=args.mode or "persistent",
        packs=args.packs or "",
        harness=args.harness or "manual",
        hardware_target=getattr(args, "hardware", None) or "",
        non_interactive=args.non_interactive,
    )
    # Model default is resolved inside run_setup() after cfg.runner is finalized.
    return run_setup(cfg)
```

Inside `run_setup`, after the runner block resolves `cfg.runner` to a real
value, the existing model block at lines 436–444 already handles the
`cfg.model == ""` case via `_MODEL_DEFAULTS.get(cfg.runner, ...)`. Make sure
the model block treats an empty string as "use default" in both the
interactive and non-interactive paths:

**Before — model block (lines 436–444):**

```python
# 2. Model (default varies by runner)
if not cfg.non_interactive:
    cfg.model = _prompt_context(
        "  Model",
        "  Which embedding model to use. We recommend the default for your hardware.",
        default=_MODEL_DEFAULTS.get(cfg.runner, "qwen3-embedding:0.6b"),
    )
else:
    cfg.model = _MODEL_DEFAULTS.get(cfg.runner, "qwen3-embedding:0.6b")
_print(f"  Model: {cfg.model}")
```

**After:**

```python
# 2. Model (default varies by runner)
default_model = _MODEL_DEFAULTS.get(cfg.runner, "qwen3-embedding:0.6b")
if not cfg.non_interactive:
    chosen = _prompt_context(
        "  Model",
        "  Which embedding model to use. We recommend the default for your hardware.",
        default=default_model,
    )
    cfg.model = chosen or default_model
else:
    cfg.model = cfg.model or default_model
_print(f"  Model: {cfg.model}")
```

Also extend `_MODEL_DEFAULTS` so `lm-studio` resolves to a sane default
(use the same GGUF model name as `llama-server` since LM Studio loads GGUF
files):

**Before — `_MODEL_DEFAULTS` (lines 78–81):**

```python
_MODEL_DEFAULTS: dict[str, str] = {
    "ollama": "qwen3-embedding:0.6b",
    "llama-server": "Qwen3-Embedding-0.6B-Q8_0.gguf",
}
```

**After:**

```python
_MODEL_DEFAULTS: dict[str, str] = {
    "ollama": "qwen3-embedding:0.6b",
    "lm-studio": "Qwen3-Embedding-0.6B-Q8_0.gguf",
    "llama-server": "Qwen3-Embedding-0.6B-Q8_0.gguf",
}
```

---

### B4 — Hardware `.title()` rendering bug and stale `dGPU` mention

**Description.** The hardware prompt currently renders the detected value via
`detected.replace('-', ' ').title()`, which produces `"Cpu"` for `"cpu"` and
`"Apple Silicon"` for `"apple-silicon"` (fine in isolation but inconsistent
with the formal label set). The context blurb also mentions `dGPU
(nvidia/radeon)` which is not a value the user can choose. Replace with a
single label map used everywhere the hardware target is shown to the user.

**File / location.** `src/skillsmith/install/subcommands/simple_setup.py`,
hardware block around lines 507–533 and summary line at 549. Add a module-level
constant near `_MODEL_DEFAULTS` (around line 78).

**Add (new module-level constant, immediately after `_MODEL_DEFAULTS`):**

```python
_HW_LABELS: dict[str, str] = {
    "cpu": "CPU (RAM-only)",
    "nvidia": "NVIDIA GPU (CUDA)",
    "radeon": "AMD GPU (Vulkan/ROCm)",
    "apple-silicon": "Apple Silicon (Metal)",
}
```

**Before — hardware prompt (lines 507–523):**

```python
# 7. Hardware / Hosting target
if not cfg.non_interactive:
    detected = cfg.recommended_host or "cpu"
    hardware_str = _prompt_context(
        "  Hardware target",
        f"  Your system has {detected.replace('-', ' ').title()} hardware detected.\n  "
        "  This controls the embedding model build and optimization. "
        "  dGPU (nvidia/radeon) uses CUDA/ROCm acceleration. CPU uses RAM-only inference.",
        default=detected,
    )
    hardware_str = hardware_str.strip().lower()
    if hardware_str not in ("nvidia", "radeon", "apple-silicon", "cpu"):
        _print(
            f"  [red]Invalid hardware: {hardware_str}. "
            "Choose nvidia, radeon, apple-silicon, or cpu.[/red]"
        )
        return 1
    cfg.hardware_target = hardware_str
```

**After (combined with F1 reordering and N3 numbered menu — final form below
under N3):** every user-facing display of a hardware key must go through
`_HW_LABELS.get(hw, hw)`. The summary line at 549 (`_print(f"  Hardware:
{cfg.hardware_target}")`) and the post-prompt confirmation echo
(`_print(f"  Hardware: {cfg.hardware_target}")`) must both be updated:

```python
_print(f"  Hardware: {_HW_LABELS.get(cfg.hardware_target, cfg.hardware_target)}")
```

The `Host target:` debug print at line 415 may also be updated for consistency,
but it lives in a `[dim]` block during detection and is acceptable as-is. For
cleanliness, change it too:

**Before (line 415):**

```python
_print(f"  Host target: {cfg.recommended_host}")
```

**After:** Remove this line entirely — F1 moves the detected-value display
into the hardware prompt block where it belongs.

---

## 2. Flow / Ordering

### F1 — Move hardware question earlier, run detection inline

**Description.** The current wizard runs hardware detection at the very top
(Phase 0) and asks the hardware question dead last (step 7). This puts ~6
questions between detection output and the prompt that uses it, and makes the
detected value feel disconnected from the question it informs. New order:

```
runner → hardware → model → port → mode → packs → harness
```

Detection itself can still run at the top of `run_setup` (it populates
`cfg.detected_runner` and `cfg.recommended_host`, both of which downstream
steps read), but the **display** of the detected value must move next to the
hardware prompt. Immediately before the hardware menu, print:

```
Detected: NVIDIA GPU (CUDA)
```

on its own line, then the menu.

**File / location.** `src/skillsmith/install/subcommands/simple_setup.py`,
`run_setup` Phase 1 around lines 417–537.

**Concrete changes inside `run_setup`:**

1. Keep Phase 0 detection block (lines 387–415) as-is **except** delete the
   final `_print(f"  Host target: {cfg.recommended_host}")` line (415).
   The GPU/Integrated debug lines (407–411) may remain.
2. Reorder Phase 1 step blocks so the sequence is:
   1. Runner (was step 1, stays step 1)
   2. **Hardware** (was step 7, becomes step 2)
   3. Model (was step 2, becomes step 3)
   4. Port (was step 3, becomes step 4)
   5. Mode (was step 4, becomes step 5)
   6. Packs (was step 5, becomes step 6)
   7. Harness (was step 6, becomes step 7)
3. The preset-resolution call (`preset = _resolve_preset(cfg)`) currently at
   line 536 must remain **after** both runner and hardware are finalized —
   moving hardware to step 2 makes this still safe, but keep the
   `_resolve_preset` call at its current position (just before the summary
   table) so all values are committed first.

**Hardware block (final form — combines B4, F1, F2 partial, and N3):**

```python
# 2. Hardware target
detected = cfg.recommended_host or "cpu"
if not cfg.non_interactive:
    _print(f"\n  Detected: {_HW_LABELS.get(detected, detected)}")
    cfg.hardware_target = _prompt_hardware(default=detected)
else:
    if cfg.hardware_target:
        cfg.hardware_target = cfg.hardware_target.strip().lower()
        if cfg.hardware_target not in _HW_LABELS:
            _print(f"  [red]Invalid hardware: {cfg.hardware_target}.[/red]")
            return 1
    else:
        cfg.hardware_target = detected
_print(f"  Hardware: {_HW_LABELS.get(cfg.hardware_target, cfg.hardware_target)}")
```

`_prompt_hardware` is defined in N3 below.

---

### F2 — Summary deduplication (drop separate `Detected:` line)

**Description.** The summary table currently shows both
`Hardware: nvidia` and `Detected: nvidia` as two separate rows. When they
agree this is noise; when they disagree the relationship should be made
explicit on a single row.

**File / location.** `run_setup` summary block, around lines 541–551.

**Before:**

```python
_print("\n[dim]" + "─" * 40)
_print("\n[bold]Review your choices:[/bold]")
_print(f"  Runner:     {cfg.runner}")
_print(f"  Model:      {cfg.model}")
_print(f"  Port:       {cfg.port}")
_print(f"  Mode:       {cfg.mode}")
_print(f"  Packs:      {cfg.packs or '(always-on only)'}")
_print(f"  Harness:    {cfg.harness}")
_print(f"  Hardware:   {cfg.hardware_target}")
_print(f"  Preset:     {preset}")
_print(f"  Detected:   {cfg.recommended_host or 'N/A'}")
```

**After (combines F2 and F3):**

```python
_print("\n[dim]" + "─" * 40)
_print("\n[bold]Review your choices:[/bold]")
_print(f"  Runner:     {cfg.runner}")
_print(f"  Model:      {cfg.model}")
_print(f"  Port:       {cfg.port}")
_print(f"  Mode:       {cfg.mode}")
_print(f"  Packs:      {cfg.packs or '(always-on only)'}")
_print(f"  Harness:    {cfg.harness}")

hw_label = _HW_LABELS.get(cfg.hardware_target, cfg.hardware_target)
detected = cfg.recommended_host or "cpu"
if cfg.hardware_target == detected:
    _print(f"  Hardware:   {hw_label}")
else:
    detected_label = _HW_LABELS.get(detected, detected)
    _print(f"  Hardware:   {hw_label}  (detected: {detected_label})")
```

---

### F3 — Remove `Preset:` from the summary table

**Description.** `Preset:` (e.g. `nvidia-llama-server`) is the YAML filename
consumed by `write_env` — an internal implementation detail of no use to the
user reviewing their choices. Already handled in the F2 "After" block above
(the `Preset:` line is simply omitted).

The `_resolve_preset(cfg)` call at line 536 must remain because downstream
code (`write_env`, step c at line 602) still reads `cfg.preset`. We are only
removing the **display**, not the resolution.

**Before (line 537):**

```python
preset = _resolve_preset(cfg)
_print(f"  Preset: {preset}")
```

**After:**

```python
preset = _resolve_preset(cfg)
# Preset is an internal write-env detail; not shown to the user.
```

---

## 3. Numbered menus

All four numbered-menu helpers follow the same shape: render a list, prompt
`Enter number [N]:`, accept either the digit or empty-input (→ default),
validate the digit is in range, and return the canonical internal value.
Place all helpers immediately after `_prompt_context` (around line 159) and
before `_discover_packs`.

**Shared helper (add once, used by all four menus):**

```python
def _prompt_numbered(
    title: str,
    options: list[tuple[str, str]],
    default_index: int,
) -> str:
    """Render a numbered menu and return the chosen option's value.

    options: list of (value, label) pairs in display order.
    default_index: 1-based index of the default option.
    Non-TTY: returns the default's value without prompting.
    """
    if not sys.stdin.isatty():
        return options[default_index - 1][0]

    _print(f"\n  [bold]{title}[/bold]")
    for i, (_value, label) in enumerate(options, start=1):
        _print(f"    {i}. {label}")
    while True:
        raw = input(f"  Enter number [{default_index}]: ").strip()
        if not raw:
            return options[default_index - 1][0]
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]
        _print(f"  [yellow]Please enter a number between 1 and {len(options)}.[/yellow]")
```

---

### N1 — Runner prompt

**File / location.** New helper near other prompt helpers; called from the
runner block in `run_setup` (around line 422).

**Add helper:**

```python
def _prompt_runner() -> str:
    return _prompt_numbered(
        "Select inference runner:",
        [
            ("ollama", "Ollama"),
            ("lm-studio", "LM Studio"),
            ("llama-server", "llama-server (llama.cpp)"),
        ],
        default_index=1,
    )
```

**Runner block in `run_setup` (final form, combines B2, B3, N1):**

```python
# 1. Runner
if cfg.runner is None and not cfg.non_interactive:
    cfg.runner = _prompt_runner()
elif cfg.runner is None:
    cfg.runner = "ollama"
cfg.runner = cfg.runner.strip().lower()
if cfg.runner not in ("ollama", "lm-studio", "llama-server"):
    _print(
        f"  [red]Invalid runner: {cfg.runner}. "
        "Choose ollama, lm-studio, or llama-server.[/red]"
    )
    return 1
_print(f"  Runner: {cfg.runner}")
```

---

### N2 — Service mode prompt

**File / location.** New helper; called from the mode block (was line 461,
becomes step 5 after F1).

**Add helper:**

```python
def _prompt_mode() -> str:
    return _prompt_numbered(
        "Service mode:",
        [
            ("persistent", "systemd  — runs as a background service (recommended)"),
            ("manual", "manual   — you manage the service lifecycle yourself"),
        ],
        default_index=1,
    )
```

**Mode block (final form, combines N2 and W2):**

**Before (lines 461–470):**

```python
# 4. Service mode
if not cfg.non_interactive:
    cfg.mode = _prompt_context(
        "  Service mode",
        "  'persistent' runs the service as a systemd daemon. 'manual' starts it on demand.",
        default="persistent",
    )
if cfg.mode not in ("persistent", "manual"):
    _print(f"  [red]Invalid mode: {cfg.mode}. Use persistent or manual.[/red]")
    return 1
_print(f"  Mode: {cfg.mode}")
```

**After:**

```python
# 5. Service mode
if not cfg.non_interactive:
    cfg.mode = _prompt_mode()
if cfg.mode not in ("persistent", "manual"):
    _print(f"  [red]Invalid mode: {cfg.mode}. Use persistent or manual.[/red]")
    return 1
_print(f"  Mode: {cfg.mode}")
```

---

### N3 — Hardware target prompt

**File / location.** New helper; called from the hardware block (now step 2
per F1).

**Add helper:**

```python
def _prompt_hardware(default: str) -> str:
    options = [
        ("cpu", _HW_LABELS["cpu"]),
        ("nvidia", _HW_LABELS["nvidia"]),
        ("radeon", _HW_LABELS["radeon"]),
        ("apple-silicon", _HW_LABELS["apple-silicon"]),
    ]
    # 1-based index of the detected default; fall back to CPU (option 1).
    default_index = 1
    for i, (value, _label) in enumerate(options, start=1):
        if value == default:
            default_index = i
            break
    return _prompt_numbered(
        "Select hardware target:",
        options,
        default_index=default_index,
    )
```

Hardware block final form is shown in F1 above.

---

### N4 — Harness prompt

**File / location.** New helper; called from the harness block (now step 7
per F1, was lines 478–504).

The harness list lives in `wire_harness.VALID_HARNESSES`, but the display
includes a non-harness sentinel value `manual` (skip) and a display alias
`continue` that maps to `continue-closed`. To keep the menu stable and
ordered, hardcode the list. `manual` is the default and rendered as the
last numbered option (not `0`) so it falls under the same numeric range
as the others.

**Add helper:**

```python
_HARNESS_OPTIONS: list[tuple[str, str]] = [
    ("claude-code", "Claude Code CLI (Anthropic)"),
    ("gemini-cli", "Gemini CLI (Google)"),
    ("cursor", "Cursor IDE"),
    ("windsurf", "Windsurf IDE"),
    ("github-copilot", "GitHub Copilot (VS Code)"),
    ("hermes-agent", "Hermes Agent"),
    ("continue-closed", "Continue.dev extension"),
    ("opencode", "OpenCode (with local LLM)"),
    ("aider", "Aider"),
    ("cline", "Cline"),
    ("manual", "manual — skip (configure later)"),
]


def _prompt_harness() -> str:
    # Default is "manual" — the last entry.
    default_index = len(_HARNESS_OPTIONS)
    return _prompt_numbered(
        "Select IDE harness:",
        _HARNESS_OPTIONS,
        default_index=default_index,
    )
```

**Harness block (final form):**

**Before (lines 477–504):**

```python
# 6. Harness
if not cfg.non_interactive:
    cfg.harness = _prompt_context(
        "  IDE harness",
        "  Wire SkillsSmith into your coding assistant:\n"
        "    claude-code    - Claude Code CLI (Anthropic)\n"
        # ... long blurb ...
        "    manual         - Skip (configure later)",
        default="manual",
    )
# Normalize "continue" display alias → actual harness names
h = cfg.harness.strip().lower()
if h == "continue":
    cfg.harness = "continue-closed"
elif h not in VALID_HARNESSES:
    _print(
        f"  [red]Invalid harness: {cfg.harness}. Choices: {', '.join(sorted(VALID_HARNESSES))}[/red]"
    )
    return 1
_print(f"  Harness: {cfg.harness}")
```

**After:**

```python
# 7. Harness
if not cfg.non_interactive:
    cfg.harness = _prompt_harness()
else:
    # Normalize CLI-provided value: accept "continue" alias and validate.
    h = (cfg.harness or "manual").strip().lower()
    if h == "continue":
        h = "continue-closed"
    cfg.harness = h

if cfg.harness != "manual" and cfg.harness not in VALID_HARNESSES:
    _print(
        f"  [red]Invalid harness: {cfg.harness}. "
        f"Choices: {', '.join(sorted(VALID_HARNESSES))}, manual[/red]"
    )
    return 1
_print(f"  Harness: {cfg.harness}")
```

Note: `manual` is intentionally accepted even though it is not in
`VALID_HARNESSES` — the existing logic at line 675 (`if cfg.harness and
cfg.harness != "manual":`) skips wiring when `manual` is selected.

---

## 4. Wording fixes

### W1 — Port question

**File / location.** Port block around lines 447–457 (becomes step 4 after F1).

**Before:**

```python
# 3. Port
if not cfg.non_interactive:
    port_str = _prompt_context(
        "  Service port",
        "  Confirms which port you want to host the FastAPI service on.",
        default=47950,
    )
```

**After:**

```python
# 4. Port
if not cfg.non_interactive:
    port_str = _prompt_context(
        "  Service port [default: 47950]",
        "  Port the skillsmith FastAPI service will listen on (default: 47950)",
        default=47950,
    )
```

---

### W2 — Service mode `manual` description

Handled by the new N2 menu labels (the `manual` row now reads
`"manual   — you manage the service lifecycle yourself"`). The pre-N2 wording
`"starts it on demand"` is gone with the free-text prompt.

---

### W3 — Consistent `[default]` marker

**Description.** The shared `_prompt_numbered` helper already renders
`Enter number [N]:` for every numbered menu. Free-text prompts that retain a
default (model, port, confirm) should show `[default: ...]` inline in the
prompt label so the value is visible regardless of whether the user is paying
attention to the `_prompt_context` `[default]` parenthetical.

The existing `_prompt` helper renders `f"{text} [{default}]: "` — i.e. it
already appends `[default]`. So the requirement is just to make the
**label** explicit where useful. Apply only where it improves clarity:

- Port label updated in W1.
- Model label: leave as-is — `_prompt_context` already appends `[<default>]`.
- Confirm prompt at line 554: leave as-is — `[y]` is already shown.

No additional code changes needed for W3 beyond W1.

---

## Implementation order

Make edits in this sequence to minimize churn and merge conflicts between
related blocks (each block's "After" code above already assumes the earlier
steps have landed):

1. **Module-level constants and helpers (top of file, no behavior change yet).**
   - Add `_HW_LABELS` after `_MODEL_DEFAULTS` (B4).
   - Extend `_MODEL_DEFAULTS` with the `lm-studio` entry (B3 consequence).
   - Add `_prompt_numbered`, `_prompt_runner`, `_prompt_mode`,
     `_prompt_hardware`, `_HARNESS_OPTIONS`, `_prompt_harness` after
     `_prompt_context` (N1–N4).

2. **Dataclass and argparse surface.**
   - `SetupConfig.runner: str | None = None` (B3).
   - `add_parser` `--runner` choices include `lm-studio` (B1).
   - `_run_from_args` stops coalescing `args.runner` to `"ollama"` and
     defers model default resolution (B3).

3. **Phase 0 (detection) cleanup.**
   - Delete the trailing `_print(f"  Host target: {cfg.recommended_host}")`
     line (F1).

4. **Phase 1 (gather config) — replace each block in the new order.** Do
   these in top-down order in the file so line offsets stay predictable:
   1. Runner block → final form (B2 + B3 + N1).
   2. Insert **new** hardware block (F1 + B4 + N3) immediately after the
      runner block.
   3. Model block → reads `cfg.model or default_model` (B3 follow-up).
   4. Port block → updated label and blurb (W1).
   5. Mode block → numbered menu (N2 + W2).
   6. Packs block → unchanged (out of scope).
   7. Harness block → numbered menu (N4); delete the now-orphaned old
      hardware block that was step 7.

5. **Phase 2 (summary).**
   - Drop the `Preset:` and standalone `Detected:` lines.
   - Replace the `Hardware:` line with the conditional
     "matches detected" / "overrode detected" rendering (F2 + F3).
   - Remove the `_print(f"  Preset: {preset}")` after `_resolve_preset`
     (F3); keep the `_resolve_preset(cfg)` call itself.

6. **Validation.**
   - Manual sanity run: `skillsmith setup --non-interactive --runner lm-studio`
     should now succeed at argparse layer.
   - Manual sanity run: `skillsmith setup` interactive — confirm question
     order is runner → hardware → model → port → mode → packs → harness,
     each numbered menu accepts blank-for-default and rejects out-of-range
     digits, and the summary shows a single `Hardware:` line with the
     `(detected: …)` suffix only when the user overrode detection.
   - `skillsmith setup --runner ollama` (interactive) must now still prompt
     for a runner only if the user **omitted** `--runner`; passing
     `--runner ollama` explicitly should skip the prompt (B3 acceptance test).

7. **Lint / type-check** the file with the project's standard tools
   (`ruff`, `mypy`) — the `str | None` change on `SetupConfig.runner` plus
   the new helpers may surface previously-silent typing issues.
